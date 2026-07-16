import asyncio
import sys
from datetime import datetime
from scraper import scrape_ads_from_search
from ai_processor import generate_hook_and_angle
from airtable_client import upload_ad_to_airtable

async def main(niche: str, country_code: str = "FR", max_ads: int = 15, min_days: int = 30, ai_filter: str = ""):
    print(f"=== Début du scraping pour la niche : '{niche}' (Pays : {country_code}, Max Pubs : {max_ads}, Min Jours : {min_days}, Filtre IA: '{ai_filter}') ===")
    
    # On extrait directement les publicités pertinentes depuis la page de recherche globale
    ads = await scrape_ads_from_search(niche, country_code=country_code, target_total_ads=max_ads, min_days_active=min_days)
    
    if not ads:
        print("Aucune publicité trouvée ou extractible pour cette niche.")
        return
        
    print(f"\n✅ {len(ads)} publicités extraites de la page. Début du traitement IA et envoi vers Airtable...")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    for ad in ads:
        print(f"\n-> Traitement de la publicité {ad.get('Ad ID')} de l'annonceur '{ad.get('Page annonceur')}'...")
        
        format_pub = ad.get("Format", "Image")
        transcript = ""
        video_url = ad.get("Media Path", "") # Scraper a mis le video_url ici si c'est une video
        img_url = ad.get("Image URL", "")
        
        if format_pub == "Vidéo":
            transcript = "Transcript non généré (Veuillez utiliser le bouton Airtable pour déclencher Whisper)."
            print("   [IA] Vidéo détectée. En attente d'une action manuelle pour Whisper.")
        else:
            print(f"   [IA] Média {format_pub} détecté : Aucun transcript nécessaire.")
            
        print("   [IA] Génération du Hook et de l'Angle via GPT-4o (sur la base du texte uniquement)...")
        ia_result = generate_hook_and_angle(transcript, ad.get("Copy complet", ""), ai_filter)
        
        is_relevant = ia_result.get("is_relevant", True)
        if not is_relevant:
            reason = ia_result.get("rejection_reason", "Non pertinent selon le filtre IA.")
            print(f"   ❌ Rejetée par l'IA : {reason}")
            continue
            
        hook = ia_result.get("hook", "")
        angle = ia_result.get("angle", "")
        
        # Le champ 'Media Path' du scraper contient soit la vidéo soit l'image
        media_url = video_url if video_url else img_url
        vignette_csv = img_url
        media_csv = media_url
        
        airtable_record = {
            "Ad ID": ad.get("Ad ID"),
            "Client / Niche": niche,
            "Page annonceur": ad.get("Page annonceur"),
            "Format": format_pub,
            "Date de début": ad.get("Date de début"),
            "Statut": ad.get("Statut", "Active"),
            "Hook": hook,
            "Transcript complet": transcript,
            "CTA": ad.get("CTA", ""),
            "Angle / résumé": angle,
            "Lien snapshot": ad.get("Lien snapshot", ""),
            "Date de scraping": today_str
        }
        
        if ad.get("Date de fin"):
            airtable_record["Date de fin"] = ad.get("Date de fin")
            

        
        # 1. Tentative d'upload API
        if img_url:
            airtable_record["Vignette"] = img_url
        if media_url:
            airtable_record["Média"] = media_url
            
        upload_ad_to_airtable(airtable_record)
        
    print("=== Scraping terminé avec succès ! ===")

if __name__ == "__main__":
    niche_keyword = sys.argv[1] if len(sys.argv) > 1 else "yoga"
    country_code = sys.argv[2] if len(sys.argv) > 2 else "FR"
    max_ads_arg = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    min_days_arg = int(sys.argv[4]) if len(sys.argv) > 4 else 30
    ai_filter_arg = sys.argv[5] if len(sys.argv) > 5 else ""
    asyncio.run(main(niche_keyword, country_code, max_ads_arg, min_days_arg, ai_filter_arg))
