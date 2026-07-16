import asyncio
from playwright.async_api import async_playwright
import time
import re
from datetime import datetime

def parse_fb_date(date_str):
    if not date_str: return None
    months = {
        'jan': 1, 'fév': 2, 'mars': 3, 'avr': 4, 'mai': 5, 'juin': 6,
        'juil': 7, 'août': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'déc': 12
    }
    parts = date_str.lower().strip().split()
    if len(parts) >= 3:
        try:
            day = int(re.sub(r'\D', '', parts[0]))
            month_str = parts[1][:4]
            month = next((v for k, v in months.items() if k in month_str), 1)
            year = int(parts[2])
            return datetime(year, month, day)
        except Exception:
            return None
    return None

async def accept_cookies(page):
    try:
        buttons = await page.get_by_role("button", name=re.compile("Autoriser|Accept|Allow", re.IGNORECASE)).all()
        for button in buttons:
            if await button.is_visible():
                await button.click()
                await asyncio.sleep(1)
                break
    except Exception:
        pass

async def scrape_ads_from_search(niche: str, country_code: str = "FR", target_total_ads: int = 15, min_days_active: int = 30):
    """
    Lance une recherche globale sur Facebook Ad Library avec le mot-clé (niche)
    et récupère les données des premières publicités trouvées (jusqu'à target_total_ads).
    """
    scraped_ads = []
    seen_ad_ids = set()

    async with async_playwright() as p:
            # En environnement serveur (Docker/Render), il FAUT utiliser headless=True car il n'y a pas d'interface graphique
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'])
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        # URL de la bibliotheque publicitaire (recherche par mot-clé)
        search_url = f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country={country_code}&media_type=all&q={niche}&search_type=keyword_unordered"
        
        print(f"Navigation vers la Meta Ads Library pour : {niche}")
        try:
            await page.goto(search_url, timeout=60000)
            await accept_cookies(page)
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
            
        await asyncio.sleep(5)
        
        scroll_attempts = 0
        while len(scraped_ads) < target_total_ads and scroll_attempts < 15:
            # Récupérer toutes les cartes contenant "ID" (identifiant la pub)
            cards = await page.locator("div:has-text('ID')").all()
            
            for card in cards:
                try:
                    text = await card.inner_text(timeout=1000)
                except Exception:
                    continue
                
                # Filtrer les conteneurs trop petits ou non-pertinents
                if not text or len(text) < 100 or "ID" not in text:
                    continue
                    
                # Chercher l'ID de la pub
                ad_id_match = re.search(r"ID[^\d]*(\d{10,})", text)
                if not ad_id_match:
                    continue
                    
                ad_id = ad_id_match.group(1)
                if ad_id in seen_ad_ids:
                    continue
                    
                # Extraire le lien de l'annonceur et son nom
                advertiser_link = ""
                advertiser_name = "Annonceur inconnu"
                
                # Chercher le premier lien dans l'en-tete de la carte
                try:
                    profile_links = await card.locator("a").all()
                    for alink in profile_links:
                        ahref = await alink.get_attribute("href")
                        aname = await alink.inner_text()
                        if ahref and "facebook.com" in ahref and aname and len(aname.strip()) > 1:
                            if "ads/library" not in ahref:
                                advertiser_name = aname.strip()
                                advertiser_link = ahref
                                break
                except Exception:
                    pass
                
                if advertiser_name == "Annonceur inconnu":
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    if len(lines) > 0:
                        for line in lines:
                            if len(line) > 1 and line not in ["Sponsorisé", "Actif", "Inactive"] and "ID" not in line and "diffusée" not in line:
                                advertiser_name = line
                                break
                
                # Format et Media
                format_pub = "Image"
                is_video = await card.locator("video").count() > 0
                imgs_count = await card.locator("img").count()
                
                if is_video:
                    format_pub = "Vidéo"
                elif imgs_count > 2: # Une pour le profil, les autres pour le contenu
                    format_pub = "Carousel"
                
                # Extraire l'image de la vignette ou pub (on ignore les petits logos < 100px)
                image_url = ""
                try:
                    imgs = await card.locator("img").all()
                    for img in imgs:
                        src = await img.get_attribute("src")
                        box = await img.bounding_box()
                        if src and "http" in src and box and box['width'] > 80 and box['height'] > 80:
                            image_url = src
                            break
                except Exception:
                    pass
                    
                # Statut et Dates
                status = "Terminée" if "Inactif" in text or "Inactive" in text else "Active"
                start_date = datetime.now().strftime("%Y-%m-%d")
                end_date = ""
                
                # Chercher toutes les dates du type "8 fév 2026" dans le texte
                date_pattern = r"(\d{1,2}\s+[a-zA-Z-éû]+\.?\s+\d{4})"
                dates_found = re.findall(date_pattern, text, re.IGNORECASE)
                
                if len(dates_found) >= 1:
                    start_date = dates_found[0]
                if len(dates_found) >= 2:
                    end_date = dates_found[1]
                
                # Calcul de la duree (filtre jours actifs)
                start_dt = parse_fb_date(start_date)
                end_dt = parse_fb_date(end_date) if end_date else datetime.now()
                
                jours_actifs = None
                if start_dt:
                    days_active = (end_dt - start_dt).days
                    jours_actifs = days_active
                    if days_active < min_days_active:
                        continue # On ignore les pubs trop recentes
                
                # Copy complet
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                copy_lines = []
                for l in lines:
                    l_lower = l.lower()
                    if "a propos" in l_lower or "about" in l_lower or "diffusée" in l_lower or "bibliothèque" in l_lower or "ad library" in l_lower or "marque" in l_lower or "voir les détails" in l_lower:
                        continue
                    if len(l) > 15:
                        copy_lines.append(l)
                
                copy_complet = "\n".join(copy_lines)
                if not copy_complet or len(copy_complet) < 5:
                    copy_complet = "Pas de texte publicitaire détecté."
                if len(copy_complet) < 5:
                    continue
                
                # Extraire le Call To Action (CTA)
                KNOWN_CTAS = ["En savoir plus", "S'inscrire", "Acheter", "Réserver", "Nous contacter", "Profiter de l'offre", "Voir plus", "Télécharger", "Envoyer un message", "Obtenir l'offre", "Postuler", "S'abonner", "Learn More", "Sign Up", "Shop Now", "Book Now", "Contact Us", "Commander", "Jouer au jeu", "Installer", "S'abonner"]
                cta_text = "En savoir plus" # Par défaut
                try:
                    # Le CTA est generalement a la fin du texte recupere dans l'iframe
                    lines_for_cta = [l.strip() for l in text.split('\n') if l.strip()]
                    # On check les 5 dernieres lignes
                    for line in reversed(lines_for_cta[-5:]):
                        for cta in KNOWN_CTAS:
                            if cta.lower() in line.lower():
                                cta_text = cta
                                break
                        if cta_text != "En savoir plus":
                            break
                except Exception:
                    pass
                
                # Extraire l'URL de la video si existante
                video_url = ""
                try:
                    if is_video:
                        videos = await card.locator("video").all()
                        for v in videos:
                            src = await v.get_attribute("src")
                            if src and "http" in src:
                                video_url = src
                                break
                except Exception:
                    pass
                
                ad_data = {
                    "Ad ID": ad_id,
                    "Page annonceur": f"{advertiser_name} ({advertiser_link})" if advertiser_link else advertiser_name,
                    "Format": format_pub,
                    "Date de début": start_dt.strftime("%Y-%m-%d") if start_dt else start_date,
                    "Date de fin": parse_fb_date(end_date).strftime("%Y-%m-%d") if end_date and parse_fb_date(end_date) else end_date,
                    "Jours actifs": jours_actifs,
                    "Statut": status,
                    "Copy complet": copy_complet,
                    "Media Path": video_url if is_video and video_url else image_url,
                    "Image URL": image_url,
                    "CTA": cta_text,
                    "Lien snapshot": f"https://www.facebook.com/ads/library/?id={ad_id}"
                }
                
                scraped_ads.append(ad_data)
                seen_ad_ids.add(ad_id)
                print(f"-> Publicité extraite : {advertiser_name} (ID: {ad_id})")
                
                if len(scraped_ads) >= target_total_ads:
                    break
            
            # Scroller pour charger la suite
            await page.mouse.wheel(0, 3000)
            await asyncio.sleep(4)
            scroll_attempts += 1
            
        await browser.close()
        
    return scraped_ads
