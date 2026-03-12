import os
import datetime
import base64

def _image_to_base64(filepath: str) -> str:
    """Converts a local image file to a base64 string for direct HTML embedding."""
    try:
        with open(filepath, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode('utf-8')
            ext = os.path.splitext(filepath)[1].lower().replace('.', '')
            if ext == 'jpg': ext = 'jpeg'
            return f"data:image/{ext};base64,{encoded}"
    except Exception as e:
        return ""

def generate_interactive_report(output_dir: str, original_script: list, generation_results: dict, supabase_url: str, supabase_key: str) -> str:
    """
    Generates a dark-mode interactive HTML QC report.
    Embeds the images as base64 so the HTML file is fully standalone.
    Injects Supabase JS hooks to submit feedback automatically.
    """
    session_id = os.path.basename(output_dir)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>QC Report - {session_id}</title>
        <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
        <style>
            :root {{
                --bg-color: #121212;
                --text-color: #E0E0E0;
                --card-bg: #1E1E1E;
                --accent-color: #BB86FC;
                --success: #03DAC6;
                --error: #CF6679;
                --border-color: #333;
            }}
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: var(--bg-color);
                color: var(--text-color);
                margin: 0;
                padding: 40px 20px;
                line-height: 1.6;
            }}
            .container {{
                max-width: 1000px;
                margin: 0 auto;
            }}
            .header {{
                text-align: center;
                margin-bottom: 50px;
            }}
            .header h1 {{
                color: var(--accent-color);
                margin-bottom: 10px;
            }}
            .scene-card {{
                background-color: var(--card-bg);
                border: 1px solid var(--border-color);
                border-radius: 12px;
                padding: 24px;
                margin-bottom: 30px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.3);
                display: flex;
                flex-direction: column;
                gap: 20px;
            }}
            .scene-meta {{
                border-bottom: 1px solid var(--border-color);
                padding-bottom: 15px;
            }}
            .scene-meta h3 {{
                margin: 0 0 10px 0;
                color: var(--success);
            }}
            .prompt-box {{
                background: #2D2D2D;
                padding: 15px;
                border-radius: 8px;
                font-family: monospace;
                font-size: 0.9em;
                white-space: pre-wrap;
            }}
            .image-container {{
                width: 100%;
                text-align: center;
            }}
            .image-container img {{
                max-width: 100%;
                border-radius: 8px;
                max-height: 500px;
                object-fit: contain;
            }}
            .feedback-section {{
                display: flex;
                flex-direction: column;
                gap: 15px;
                background: #252525;
                padding: 20px;
                border-radius: 8px;
                margin-top: 10px;
            }}
            .button-group {{
                display: flex;
                gap: 15px;
            }}
            button {{
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-weight: bold;
                transition: transform 0.1s;
                font-size: 14px;
            }}
            button:active {{ transform: scale(0.98); }}
            .btn-approve {{ background-color: var(--success); color: #000; }}
            .btn-reject {{ background-color: var(--error); color: #FFF; }}
            .btn-approve.active {{ box-shadow: 0 0 0 3px #fff; }}
            .btn-reject.active {{ box-shadow: 0 0 0 3px #fff; }}
            
            textarea {{
                width: 100%;
                background: #333;
                color: white;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 10px;
                font-family: inherit;
                resize: vertical;
                min-height: 80px;
                box-sizing: border-box;
                display: none;
            }}
            .submit-btn {{
                background-color: var(--accent-color);
                color: #000;
                font-size: 18px;
                padding: 15px 40px;
                width: 100%;
                margin-top: 40px;
                border-radius: 8px;
            }}
            #status-overlay {{
                position: fixed;
                top: 0; left: 0; width: 100%; height: 100%;
                background: rgba(0,0,0,0.8);
                display: none;
                justify-content: center;
                align-items: center;
                z-index: 1000;
            }}
            .spinner-box {{
                background: var(--card-bg);
                padding: 40px;
                border-radius: 12px;
                text-align: center;
                border: 1px solid var(--accent-color);
            }}
        </style>
    </head>
    <body>
        
        <div id="status-overlay">
            <div class="spinner-box">
                <h2 id="status-text" style="color: var(--accent-color);">Submitting Feedback...</h2>
                <p id="status-subtext">Please wait.</p>
            </div>
        </div>

        <div class="container">
            <div class="header">
                <h1>Psimplicity QC Report</h1>
                <p>Session: <strong>{session_id}</strong> | Generated: {timestamp}</p>
                <p>Please review the generated images below. Approve them, or request specific changes.</p>
            </div>
            
            <div id="scenes-container">
    """

    for scene in original_script:
        scene_id = scene.get('id', 'Unknown')
        original_desc = scene.get('description', '')
        
        # Look up generation results for this specific scene ID
        result = generation_results.get(scene_id, {})
        status = result.get('status', 'not_generated')
        prompt_used = result.get('prompt', 'N/A')
        image_path = result.get('path', '')
        error_msg = result.get('error', '')
        
        if status == 'success' and image_path:
            # Embed image directly into HTML so it won't break when emailed/moved
            b64_image = _image_to_base64(image_path)
            image_html = f'<div class="image-container"><img src="{b64_image}" alt="Scene {scene_id}"></div>'
        else:
            image_html = f'<div class="prompt-box" style="color:red;">Failed to generate: {error_msg}</div>'


        html_content += f"""
                <div class="scene-card" data-scene-id="{scene_id}">
                    <div class="scene-meta">
                        <h3>Scene {scene_id}</h3>
                        <strong>Original Script:</strong> {original_desc}
                    </div>
                    
                    <div>
                        <strong>Generated Prompt:</strong>
                        <div class="prompt-box">{prompt_used}</div>
                    </div>
                    
                    {image_html}
                    
                    <div class="feedback-section">
                        <div class="button-group">
                            <button class="btn-approve" onclick="setFeedback('{scene_id}', 'approve')">✅ Approve</button>
                            <button class="btn-reject" onclick="setFeedback('{scene_id}', 'reject')">❌ Request Change</button>
                        </div>
                        <textarea id="notes-{scene_id}" placeholder="Type exactly what needs to be changed for this image..."></textarea>
                    </div>
                </div>
        """

    html_content += f"""
            </div>
            <button class="submit-btn" onclick="submitToSupabase()">Submit All Feedback 🚀</button>
        </div>

        <script>
            // Initialize Supabase Client
            const supabaseUrl = '{supabase_url}';
            const supabaseKey = '{supabase_key}';
            const supabase = supabase.createClient(supabaseUrl, supabaseKey);
            const sessionId = '{session_id}';
            
            // State to store feedback
            const feedbackData = {{}};

            function setFeedback(sceneId, status) {{
                // Update state
                if (!feedbackData[sceneId]) feedbackData[sceneId] = {{}};
                feedbackData[sceneId].status = status;
                
                // Update UI Buttons
                const card = document.querySelector(`.scene-card[data-scene-id="${{sceneId}}"]`);
                const btnApprove = card.querySelector('.btn-approve');
                const btnReject = card.querySelector('.btn-reject');
                const textArea = card.querySelector('textarea');
                
                if (status === 'approve') {{
                    btnApprove.classList.add('active');
                    btnReject.classList.remove('active');
                    textArea.style.display = 'none';
                    textArea.value = ''; // Clear notes on approve
                }} else {{
                    btnReject.classList.add('active');
                    btnApprove.classList.remove('active');
                    textArea.style.display = 'block';
                    textArea.focus();
                }}
            }}

            async function submitToSupabase() {{
                // Gather final notes and validate
                const payload = [];
                let missingResponses = false;
                
                document.querySelectorAll('.scene-card').forEach(card => {{
                    const sceneId = card.getAttribute('data-scene-id');
                    const status = feedbackData[sceneId]?.status;
                    const notes = card.querySelector('textarea').value;
                    
                    if (!status) {{
                        missingResponses = true;
                    }}
                    
                    payload.push({{
                        session_id: sessionId,
                        scene_id: sceneId,
                        status: status || 'pending',
                        notes: status === 'reject' ? notes : '',
                        created_at: new Date().toISOString()
                    }});
                }});
                
                if (missingResponses) {{
                    const proceed = confirm("You haven't approved or rejected all scenes. Submit anyway?");
                    if (!proceed) return;
                }}
                
                // Show loading UI
                document.getElementById('status-overlay').style.display = 'flex';
                
                try {{
                    // Insert into Supabase table 'qc_feedback'
                    const {{ data, error }} = await supabase
                        .from('qc_feedback')
                        .insert(payload);
                        
                    if (error) throw error;
                    
                    document.getElementById('status-text').innerText = "✅ Success!";
                    document.getElementById('status-text').style.color = "var(--success)";
                    document.getElementById('status-subtext').innerText = "Your feedback has been submitted to the agency. You can close this window.";
                    
                }} catch (err) {{
                    console.error("Supabase Error:", err);
                    document.getElementById('status-text').innerText = "❌ Submission Failed";
                    document.getElementById('status-text').style.color = "var(--error)";
                    document.getElementById('status-subtext').innerText = err.message || "Please check your internet connection and try again.";
                    
                    // Allow retry
                    setTimeout(() => {{
                        document.getElementById('status-overlay').style.display = 'none';
                    }}, 3000);
                }}
            }}
        </script>
    </body>
    </html>
    """
    
    report_path = os.path.join(output_dir, "QC_Report.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    return report_path
