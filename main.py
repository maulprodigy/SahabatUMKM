import os
import base64
import asyncio
import json
from datetime import datetime
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# --- TAMBAHAN GOOGLE SHEETS ---
import gspread

# 1. KTP Vertex AI & Google Sheets
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "kunci-gcp.json"

from google import genai
from google.genai import types 
from vertexai.preview.vision_models import ImageGenerationModel
import vertexai

# --- KONFIGURASI AI ---
# Mengambil API Key secara aman dari server (Environment Variable)
API_KEY = os.environ.get("GEMINI_API_KEY")
client_teks = genai.Client(api_key=API_KEY)
GCP_PROJECT_ID = "gen-lang-client-0660910063" # WAJIB PAKAI ID YANG BARU INI!
GCP_LOCATION = "us-central1"
vertexai.init(project=GCP_PROJECT_ID, location=GCP_LOCATION)
image_model = ImageGenerationModel.from_pretrained("imagen-4.0-generate-001")

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- INISIALISASI GOOGLE SHEETS ---
try:
    # Koneksi pakai kunci GCP yang sama
    gc = gspread.service_account(filename="kunci-gcp.json")
    
    # MASUKKAN ID SPREADSHEET KAMU DI SINI (Ganti teks di dalam tanda kutip)
    SPREADSHEET_ID = "1K0aPVelYuk8tj1w5MQR2WOcbWufQcV8hNVIFge_rgNQ" 
    
    sh = gc.open_by_key(SPREADSHEET_ID)
    worksheet = sh.sheet1 # Menggunakan tab pertama (Sheet1)
    print("📊 GOOGLE SHEETS TERHUBUNG SIAP TEMPUR!")
except Exception as e:
    print(f"❌ GAGAL KONEK GOOGLE SHEETS: {e}")

# --- KODE AI TETAP SAMA ---
class IdeBisnis(BaseModel):
    deskripsi: str
    input_image_base64: Optional[str] = None 

async def generate_text_async(data: IdeBisnis):
    instruction = f"Kamu adalah pakar marketing UMKM di Cilegon. Analisis ide ini: '{data.deskripsi}'."
    contents_parts = [instruction]
    if data.input_image_base64:
        header, encoded = data.input_image_base64.split(",", 1)
        mime_type = header.split(":")[1].split(";")[0]
        contents_parts.append(types.Part.from_bytes(data=base64.b64decode(encoded), mime_type=mime_type))
    contents_parts.append("""Berikan hasil dalam format JSON murni: {"nama": "Nama Usaha", "slogan": "Slogan Usaha", "promosi": "Teks promosi Instagram"}""")
    response = await client_teks.aio.models.generate_content(model='gemini-3.1-flash-lite', contents=contents_parts)
    clean_text = response.text.strip().replace('```json', '').replace('```', '')
    return json.loads(clean_text)

async def generate_image_async(deskripsi: str, nama_usaha: str):
    prompt_image = f"Professional product photography of {deskripsi} for '{nama_usaha}' in Cilegon. Aesthetic cafe background."
    images = await asyncio.to_thread(image_model.generate_images, prompt=prompt_image, number_of_images=1)
    base64_image = base64.b64encode(images[0]._image_bytes).decode("utf-8")
    return f"data:image/png;base64,{base64_image}"

@app.post("/generate-bisnis")
async def buat_profil_bisnis_hardcore(data: IdeBisnis):
    text_data = await generate_text_async(data)
    final_image = await generate_image_async(data.deskripsi, text_data['nama'])
    return {**text_data, "logo_base64": final_image}

# --- ENDPOINT DAFTAR (UPDATE KE GOOGLE SHEETS) ---
class DataPendaftar(BaseModel):
    nama: str
    whatsapp: str
    password: str

@app.post("/daftar")
async def daftar_user(data: DataPendaftar):
    try:
        print(f"📩 MENERIMA DATA: {data.nama} ({data.whatsapp})")
        
        # Ambil waktu saat ini
        waktu_sekarang = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Tambahkan baris baru ke paling bawah Google Sheets
        worksheet.append_row([waktu_sekarang, data.nama, data.whatsapp, data.password])
        
        print(f"✅ SUKSES: Data {data.nama} sudah masuk ke Google Sheets!")
        return {"status": "sukses", "pesan": "Data berhasil meluncur ke Google Sheets!"}
    except Exception as e:
        print(f"❌ ERROR SAAT SIMPAN KE SHEETS: {str(e)}")
        return {"status": "error", "pesan": str(e)}
# --- TAMBAHAN SCHEMA UNTUK CHATBOT ---
class PesanChat(BaseModel):
    pesan: str
    history: list = [] # Untuk menyimpan memori obrolan

# --- ENDPOINT CHATBOT BRAINSTORMING ---
@app.post("/chat-brainstorming")
async def chat_brainstorming(data: PesanChat):
    try:
        # Kita gabungkan history obrolan jadi satu teks panjang biar pintar dan nyambung
        percakapan = [
            "INSTRUKSI SISTEM: Kamu adalah 'Bess', asisten AI pintar dan gaul khusus UMKM di Cilegon. Tugasmu membantu user brainstorming ide bisnis, strategi marketing, atau nama usaha. Jawab dengan bahasa santai, asik, suportif, dan solutif. Jangan terlalu panjang, langsung ke intinya saja.",
        ]

        # Masukkan riwayat obrolan sebelumnya
        for chat in data.history:
            percakapan.append(f"{chat['role']}: {chat['text']}")

        # Masukkan pesan terbaru dari user
        percakapan.append(f"USER: {data.pesan}")
        percakapan.append("BESS:")

        # Jadikan satu prompt utuh
        prompt_final = "\n".join(percakapan)

        # Minta Gemini untuk membalas
        response = await client_teks.aio.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=prompt_final
        )

        return {"status": "sukses", "balasan": response.text.strip()}
    except Exception as e:
        print(f"❌ ERROR CHAT: {str(e)}")
        return {"status": "error", "balasan": "Waduh, sinyal otak AI lagi nyangkut nih Bess. Coba ketik lagi ya!"}

# Pastikan app.mount ini di atas if __name__
app.mount("/", StaticFiles(directory="public", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)