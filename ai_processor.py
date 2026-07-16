import os
import requests
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def download_video(url: str, output_path: str) -> bool:
    """Télécharge une vidéo depuis une URL."""
    if not url or not url.startswith("http"):
        return False
    try:
        r = requests.get(url, stream=True, timeout=10)
        if r.status_code == 200:
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
            return True
    except Exception:
        pass
    return False

def transcribe_audio(file_path: str) -> str:
    """
    Transcrit un fichier audio/video en texte avec Whisper.
    """
    if not os.path.exists(file_path):
        return ""
    
    try:
        with open(file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file
            )
        
        text = transcript.text.strip()
        if not text or len(text) < 5:
            return "Musique d'ambiance uniquement."
        return text
    except Exception as e:
        print(f"Erreur lors de la transcription Whisper : {e}")
        return "Erreur de transcription (fichier potentiellement invalide ou protégé)"


def generate_hook_and_angle(transcript: str, copy_text: str, ai_filter: str = "") -> dict:
    """
    Analyse le transcript et le texte de l'annonce pour en deduire
    le Hook, l'Angle/Resume marketing et valider la pertinence (Filtre IA).
    """
    filter_instruction = ""
    if ai_filter:
        filter_instruction = f"""
3. "is_relevant" : booléen (true/false). Vérifie STRICTEMENT si cette publicité respecte le critère suivant : "{ai_filter}". Si elle ne le respecte pas ou si c'est ambigu, mets false.
4. "rejection_reason" : Si is_relevant est false, explique brièvement pourquoi. Sinon, laisse vide "".
"""
    else:
        filter_instruction = """
3. "is_relevant" : true
4. "rejection_reason" : ""
"""

    prompt = f"""
Voici le texte d'une publicité (Copy) :
{copy_text}

Voici la transcription audio de la vidéo (si c'est une vidéo) :
{transcript}

TÂCHES STRICTES :
1. "hook" : Trouve et copie EXACTEMENT la toute première phrase d'accroche (celle qui sert à capter l'attention dans les 3 premières secondes). Cherche d'abord dans la transcription audio. S'il n'y a pas d'audio, prends la première phrase forte du texte (Copy). Ne la modifie pas, recopie-la.
2. "angle" : Rédige un résumé clair et concis (1 phrase maximum) sur l'angle d'approche de la publicité (ex: "Mise en avant d'une promotion limitée pour créer l'urgence", "Témoignage client pour rassurer"). Ne mets JAMAIS de date ici.
{filter_instruction}

Réponds UNIQUEMENT sous forme de JSON avec ces QUATRE clés (hook, angle, is_relevant, rejection_reason).
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={ "type": "json_object" },
            messages=[
                {"role": "system", "content": "Tu es un expert en marketing digital et en copywriting."},
                {"role": "user", "content": prompt}
            ]
        )
        
        import json
        result = json.loads(response.choices[0].message.content)
        return {
            "hook": result.get("hook", ""),
            "angle": result.get("angle", ""),
            "is_relevant": result.get("is_relevant", True),
            "rejection_reason": result.get("rejection_reason", "")
        }
    except Exception as e:
        return {"hook": "", "angle": "", "is_relevant": True, "rejection_reason": ""}

def generate_niche_report(ads_data: list, niche: str) -> str:
    """
    Génère un rapport de synthèse (Top 10 Hooks, Top 10 Angles, Script) 
    basé sur les annonces extraites d'Airtable.
    """
    if not ads_data:
        return "Aucune donnée disponible pour générer un rapport."
        
    # Construire un contexte condensé pour éviter d'exploser le token limit de l'IA
    context_lines = []
    for i, ad in enumerate(ads_data):
        fields = ad.get("fields", {})
        hook = fields.get("Hook", "")
        angle = fields.get("Angle / résumé", "")
        transcript = fields.get("Transcript complet", "")
        jours = fields.get("Jours actifs", 0)
        
        context_lines.append(f"--- ANNONCE {i+1} (Actif depuis {jours} jours) ---")
        context_lines.append(f"Hook: {hook}")
        context_lines.append(f"Angle: {angle}")
        if transcript and len(transcript) > 10:
            # On limite le transcript pour gagner de la place
            context_lines.append(f"Transcript extrait: {transcript[:500]}...")
            
    full_context = "\n".join(context_lines)
    
    prompt = f"""
Je vais te fournir les meilleures publicités actuelles pour la niche / l'annonceur suivant : "{niche}".
Ces annonces sont triées par rentabilité (celles qui tournent depuis le plus longtemps sont au début).

Voici les données brutes :
{full_context}

---
TA MISSION EN TANT QU'EXPERT COPYWRITER :
Analyse en profondeur ces annonces gagnantes et rédige un rapport de synthèse complet au format Markdown pour m'aider à créer mes propres vidéos.

Ton rapport DOIT inclure exactement les 3 sections suivantes :

### 🔥 1. Le Top 10 des Meilleurs Hooks
Sélectionne les 10 meilleures phrases d'accroche (Hooks) trouvées dans ces annonces. Pour chaque Hook, explique brièvement *pourquoi* il fonctionne psychologiquement sur cette cible.

### 🧠 2. Le Top 10 des Meilleurs Angles Marketing
Liste les 10 meilleurs angles/descriptions utilisés. Qu'est-ce qu'ils mettent en avant ? (ex: Promotion, Résultat rapide, Autorité, Preuve sociale...). Explique comment je peux les répliquer.

### 🎬 3. Le Script Vidéo "Ultime" (Template)
En te basant sur la structure des annonces qui marchent le mieux, crée un "Template de Script Vidéo" universel pour cette niche. Donne la structure seconde par seconde (ex: 0-3s : Hook visuel et oral, 3-10s : Problème, etc.) avec un exemple concret rempli.

Rédige ce rapport de manière professionnelle, directe et très formatée en Markdown.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Tu es un expert en marketing digital, media buying et copywriting spécialisé dans l'analyse de publicités Facebook/Meta."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Erreur lors de la génération du rapport : {e}")
        return f"Erreur lors de la génération du rapport : {e}"
