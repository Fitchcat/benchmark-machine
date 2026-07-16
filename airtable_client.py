import os
import re
from pyairtable import Api
from dotenv import load_dotenv

load_dotenv()

api = Api(os.getenv("AIRTABLE_API_KEY"))
base_id_env = os.getenv("AIRTABLE_BASE_ID", "")

# Extraire intelligemment l'ID de la base
match = re.search(r'(app[a-zA-Z0-9]+)', base_id_env)
if match:
    base_id = match.group(1)
else:
    base_id = base_id_env.split('/')[0] # sécurité

if base_id and not base_id.startswith("app"):
    base_id = f"app{base_id}"

table = api.table(base_id, "Ads")

def upload_ad_to_airtable(ad_data: dict):
    """
    Uploade une publicite scrape vers la table 'Ads' d'Airtable.
    
    ad_data doit contenir :
    - "Ad ID": str
    - "Page annonceur": str
    - "Format": str ("Vidéo", "Image", "Carousel")
    - "Date de début": str (YYYY-MM-DD)
    - "Statut": str ("Active" ou "Terminée")
    - "Hook (texte)": str
    - "Transcript complet": str
    - "Copy complet": str
    - "CTA": str
    - "Angle / Résumé": str
    - "Lien snapshot": str
    - "Date de scraping": str (YYYY-MM-DD)
    """
    try:
        # L'API Airtable (via pyairtable) s'attend a un dictionnaire de champs
        record = table.create(ad_data)
        print(f"✅ Ad {ad_data.get('Ad ID')} uploadée avec succès sur Airtable !")
        return record
    except Exception as e:
        print(f"❌ Erreur lors de l'upload vers Airtable pour l'Ad {ad_data.get('Ad ID')}: {e}")
        return None

def get_top_ads_for_niche(niche: str, limit: int = 50) -> list:
    """
    Récupère les meilleures annonces pour une niche donnée depuis Airtable.
    """
    try:
        # Formule Airtable pour filtrer par Niche ou Annonceur (recherche flexible)
        # On utilise FIND() pour que ça matche si la niche tapée est contenue dans "Client / Niche" ou "Page annonceur"
        formula = f"OR(FIND(LOWER('{niche}'), LOWER({{Client / Niche}})), FIND(LOWER('{niche}'), LOWER({{Page annonceur}})))"
        
        # Récupère tous les records correspondants
        records = table.all(formula=formula)
        
        # Les trier par Jours actifs (décroissant) - nécessite que Jours actifs soit un nombre dans les data renvoyées, 
        # mais Jours actifs est peut-être une string ou manquant. On trie par défaut.
        def safe_jours_actifs(rec):
            val = rec.get("fields", {}).get("Jours actifs", 0)
            try:
                return int(val)
            except:
                return 0
                
        records.sort(key=safe_jours_actifs, reverse=True)
        return records[:limit]
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des annonces Airtable: {e}")
        return []
