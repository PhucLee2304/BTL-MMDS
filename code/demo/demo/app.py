import os
import pandas as pd
import gradio as gr
from models_handler import ModelHandler

print("Initializing Model Handler...")
handler = ModelHandler()

try:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    data_path = os.path.join(BASE_DIR, "data", "raw", "taxi_zone_lookup.csv")
    zones_df = pd.read_csv(data_path)
except Exception as e:
    print(f"Không tìm thấy file csv zone: {e}. Tạo danh sách mặc định.")
    zones_df = pd.DataFrame({"LocationID": [1, 2, 3], "Zone": ["EWR", "Queens", "Bronx"]})

zone_dict = {row['LocationID']: row['Zone'] for _, row in zones_df.iterrows()}
valid_46_zones = [13, 43, 48, 50, 68, 75, 79, 87, 90, 100, 107, 113, 114, 132, 137, 138, 140, 141, 142, 143, 144, 148, 151, 158, 161, 162, 163, 164, 166, 170, 186, 211, 229, 230, 231, 233, 234, 236, 237, 238, 239, 246, 249, 262, 263, 264]

def process_prediction(date_str, hour_str, minute_str, model_name):
    if model_name in ["KShape Ensemble", "GBT Model"]:
        target_zones = list(zone_dict.keys())
    else:
        target_zones = valid_46_zones
        
    results = []
    for loc_id in target_zones:
        try:
            pred = handler.predict(model_name, loc_id, date_str, hour_str, minute_str)
            if isinstance(pred, (int, float)):
                results.append({"ID": loc_id, "Zone": zone_dict.get(loc_id, "Unknown"), "Demand": pred})
        except:
            pass
            
    if not results:
        return "<div style='color: red; text-align: center;'>Lỗi: Không dự đoán được zone nào.</div>"
        
    results.sort(key=lambda x: x["Demand"], reverse=True)
    
    html_content = "<div style='max-height: 500px; overflow-y: auto; padding-right: 10px;'>"
    for idx, r in enumerate(results):
        rank = idx + 1
        color = "#4ade80" if rank <= 3 else "#ffffff"
        bg = "rgba(74, 222, 128, 0.1)" if rank <= 3 else "rgba(255, 255, 255, 0.05)"
        
        html_content += f"""
        <div style='background: {bg}; border-radius: 8px; padding: 12px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; border: 1px solid rgba(255,255,255,0.1);'>
            <div style='display: flex; align-items: center; gap: 15px;'>
                <div style='font-size: 1.2em; font-weight: bold; color: {color}; width: 30px;'>#{rank}</div>
                <div>
                    <div style='font-weight: bold; font-size: 1.1em;'>{r['Zone']}</div>
                    <div style='font-size: 0.8em; color: #94a3b8;'>ID: {r['ID']}</div>
                </div>
            </div>
            <div style='font-size: 1.5em; font-weight: bold; color: {color};'>
                {r['Demand']:.1f} <span style='font-size: 0.5em; color: #94a3b8;'>rides</span>
            </div>
        </div>
        """
    html_content += "</div>"
    return html_content

custom_css = """
body {
    background-color: #0f172a !important; 
}
.gradio-container {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%) !important;
    color: white !important;
    font-family: 'Inter', sans-serif !important;
    border-radius: 1rem !important;
    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5) !important;
    max-width: 850px !important;
    margin: auto !important;
}
.glass-panel {
    background: rgba(255, 255, 255, 0.03) !important;
    backdrop-filter: blur(15px) !important;
    -webkit-backdrop-filter: blur(15px) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 1rem !important;
    padding: 2rem !important;
    margin-top: 1rem !important;
}
input, .gr-dropdown, .gr-box {
    background: rgba(15, 23, 42, 0.7) !important;
    border: 1px solid rgba(255,255,255,0.2) !important;
    color: white !important;
    border-radius: 0.5rem !important;
}
.predict-btn {
    background: linear-gradient(90deg, #3b82f6 0%, #8b5cf6 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: bold !important;
    font-size: 1.2em !important;
    border-radius: 0.8rem !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
    margin-top: 20px !important;
}
.predict-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 10px 20px -10px rgba(139, 92, 246, 0.8) !important;
}
.gr-markdown h1, .gr-markdown h3 {
    color: white !important;
}
"""

model_choices = [
    "KShape Ensemble",
    "Holt-Winters (XGBoost)",
    "Spatiotemporal Bundle",
    "GBT Model"
]

with gr.Blocks() as demo:
    with gr.Column(elem_classes="glass-panel"):
        gr.Markdown("<h1 style='text-align: center; font-size: 2.5em;'>🚖 NY Taxi Demand AI</h1>")
        gr.Markdown("<h3 style='text-align: center; color: #94a3b8;'>Local Prediction & Demonstration System</h3>")
        
        with gr.Row():
            with gr.Column(scale=1):
                date_input = gr.Textbox(label="Date (YYYY-MM-DD)", value="2026-05-30", placeholder="2026-05-30")
            with gr.Column(scale=1):
                hour_dropdown = gr.Dropdown(choices=[str(i).zfill(2) for i in range(24)], label="Hour (0-23)", value="12")
            with gr.Column(scale=1):
                minute_dropdown = gr.Dropdown(choices=[str(i).zfill(2) for i in range(60)], label="Minute (0-59)", value="00")
                
        with gr.Row():
            model_dropdown = gr.Dropdown(choices=model_choices, label="Select AI Model Pipeline", value="KShape Ensemble")
            
        predict_btn = gr.Button("🔮 Predict Demand", elem_classes="predict-btn", size="lg")
        
        output_html = gr.HTML(label="Demand Forecast")
        
    predict_btn.click(
        fn=process_prediction,
        inputs=[date_input, hour_dropdown, minute_dropdown, model_dropdown],
        outputs=[output_html]
    )

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, share=False, css=custom_css, theme=gr.themes.Base())
