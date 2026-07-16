from flask import Flask, render_template, request, jsonify, send_file
import subprocess
import os
import time

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/scrape", methods=["POST"])
def run_scrape():
    data = request.json
    niche = data.get("niche", "").strip()
    country = data.get("country", "FR")
    max_ads = str(data.get("maxAds", 15))
    min_days = str(data.get("minDays", 30))
    ai_filter = str(data.get("aiFilter", "")).strip()
    
    if not niche:
        return jsonify({"error": "Veuillez entrer une niche valide."}), 400
        
    try:
        # Run main.py in a subprocess with the given parameters
        print(f"Lancement du scraping pour la niche : {niche} (Pays: {country}, Max Ads: {max_ads}, Min Days: {min_days}, Filtre IA: {ai_filter})")
        # Note: We assume the venv python is used since we'll run app.py from venv
        import threading
        import asyncio
        from main import main as run_main
        import sys
        
        def background_task(niche, country, max_ads, min_days, ai_filter):
            with open("scrape.log", "w") as f:
                f.write(f"=== Début du background task pour {niche} ===\n")
                f.flush()
            
            # Rediriger stdout et stderr vers le fichier
            original_stdout = sys.stdout
            original_stderr = sys.stderr
            try:
                with open("scrape.log", "a", buffering=1) as log_file:
                    sys.stdout = log_file
                    sys.stderr = log_file
                    
                    asyncio.run(run_main(niche, country, int(max_ads), int(min_days), ai_filter))
            except Exception as e:
                with open("scrape.log", "a") as log_file:
                    log_file.write(f"\nErreur fatale dans le background task : {e}\n")
            finally:
                sys.stdout = original_stdout
                sys.stderr = original_stderr
                
        # Lancement dans un Thread pour éviter l'erreur "Out Of Memory" (SIGKILL)
        thread = threading.Thread(target=background_task, args=(niche, country, max_ads, min_days, ai_filter))
        thread.daemon = True
        thread.start()
        
        message_succes = "Le robot a bien démarré en arrière-plan ! 🚀\n\nÉtant donné que la recherche et l'analyse IA prennent environ 2 à 3 minutes, vous n'avez pas besoin d'attendre sur cette page.\n\n👉 Allez vérifier votre base Airtable pour voir les nouvelles publicités s'ajouter progressivement."
        
        return jsonify({
            "success": True, 
            "logs": message_succes
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/process_video")
def process_video():
    record_id = request.args.get("record_id")
    ad_id = request.args.get("ad_id")
    
    # Si l'utilisateur n'a pas rafraichi la page, l'ancien JS envoie record_id avec le numero Ad ID
    if record_id and not record_id.startswith("rec"):
        ad_id = record_id
        record_id = None
    
    if not record_id and not ad_id:
        return "Record ID ou Ad ID manquant.", 400
        
    try:
        from airtable_client import table
        
        if ad_id:
            # Chercher la ligne Airtable correspondant à cet Ad ID
            records = table.all(formula=f"{{Ad ID}}='{ad_id}'")
            if not records:
                return "Publicité introuvable sur Airtable avec cet Ad ID.", 404
            record = records[0]
            record_id = record["id"]
        else:
            record = table.get(record_id)
            
        fields = record.get("fields", {})
        
        media = fields.get("Média", [])
        video_url = ""
        # Gérer le cas du CSV vs Airtable natif
        if isinstance(media, list) and len(media) > 0:
            video_url = media[0].get("url")
        elif isinstance(media, str):
            video_url = media
            
        if not video_url or not video_url.startswith("http"):
            return "URL vidéo invalide ou introuvable.", 400
            
        from ai_processor import download_video, transcribe_audio, generate_hook_and_angle
        temp_video = f"temp_{record_id}.mp4"
        success = download_video(video_url, temp_video)
        
        if success:
            transcript = transcribe_audio(temp_video)
            try:
                os.remove(temp_video)
            except:
                pass
                
            ia_result = generate_hook_and_angle(transcript, fields.get("Copy complet", ""))
            
            table.update(record_id, {
                "Transcript complet": transcript,
                "Hook": ia_result.get("hook", fields.get("Hook", "")),
                "Angle / résumé": ia_result.get("angle", fields.get("Angle / résumé", ""))
            })
            
            return f"<html><body style='font-family:sans-serif;text-align:center;padding:50px;'><h2>✅ Succès !</h2><p>Le transcript a été généré via Whisper et envoyé à Airtable avec le nouveau Hook.</p><p><b>Vous pouvez fermer cette fenêtre.</b></p></body></html>"
        else:
            return "Erreur lors du téléchargement de la vidéo (vidéo potentiellement protégée ou expirée).", 500
    except Exception as e:
        return f"Erreur : {e}", 500

@app.route("/generate_report", methods=["POST"])
def generate_report():
    data = request.json
    niche = data.get("niche", "").strip()
    limit = int(data.get("limit", 50))
    
    if not niche:
        return jsonify({"error": "Veuillez entrer une niche ou un nom d'annonceur."}), 400
        
    try:
        from airtable_client import get_top_ads_for_niche
        from ai_processor import generate_niche_report
        
        # 1. Fetch ads
        ads = get_top_ads_for_niche(niche, limit)
        if not ads:
            return jsonify({"error": f"Aucune publicité trouvée sur Airtable pour '{niche}'."}), 404
            
        # 2. Generate report
        report_markdown = generate_niche_report(ads, niche)
        
        # We can use a simple markdown to html converter if needed, or return raw markdown to frontend
        import markdown
        report_html = markdown.markdown(report_markdown)
        
        return jsonify({
            "success": True,
            "report_html": report_html
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/logs")
def get_logs():
    try:
        if os.path.exists("scrape.log"):
            with open("scrape.log", "r") as f:
                return f.read()
        return "Aucun log disponible pour le moment."
    except:
        return "Erreur lors de la lecture des logs."

if __name__ == "__main__":
    app.run(debug=True, port=5000)
