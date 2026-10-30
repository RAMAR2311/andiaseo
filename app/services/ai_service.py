import os
import base64
import json
import io
from pathlib import Path
from openai import OpenAI
from pypdf import PdfReader
from PIL import Image

def get_openai_client():
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("No se ha configurado la variable OPENAI_API_KEY en el entorno o archivo .env")
    return OpenAI(api_key=api_key)

def encode_file_for_openai(file_bytes: bytes, filename: str):
    """
    Determina si el archivo es imagen o PDF.
    Si es PDF, extrae su texto o páginas de imagen si aplica.
    Para imágenes (png, jpg, webp), las codifica en Base64.
    """
    ext = filename.lower().split('.')[-1]
    
    if ext in ['jpg', 'jpeg', 'png', 'webp']:
        b64 = base64.b64encode(file_bytes).decode('utf-8')
        mime = f"image/{'jpeg' if ext in ['jpg', 'jpeg'] else ext}"
        return {
            "type": "image",
            "url": f"data:{mime};base64,{b64}"
        }
    elif ext == 'pdf':
        # Intentar extraer texto directamente del PDF
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            text_content = []
            for i, page in enumerate(reader.pages):
                extracted = page.extract_text()
                if extracted:
                    text_content.append(f"--- PÁGINA {i+1} ---\n{extracted}")
            
            full_text = "\n".join(text_content).strip()
            if len(full_text) > 40:
                return {
                    "type": "text",
                    "content": full_text
                }
        except Exception:
            pass
        
        # Si no tiene texto o falló, podemos retornar que es PDF binario o no legible por texto
        return {
            "type": "pdf_raw",
            "content": f"Documento PDF ({filename}) sin capa de texto seleccionable directa."
        }
    
    raise ValueError(f"Formato no soportado: .{ext}. Use JPG, PNG, WEBP o PDF.")

def analizar_factura_con_ai(file_bytes: bytes, filename: str, tipo_operacion: str = "compra") -> dict:
    """
    Analiza una factura de compra o de venta mediante GPT-4o-mini multimodal.
    tipo_operacion: 'compra' (para entrada/subir stock) o 'venta' (para despacho/reducir stock)
    
    Retorna un diccionario estructurado:
    {
        "numero_factura": "...",
        "fecha": "YYYY-MM-DD",
        "tercero": "Proveedor o Cliente",
        "tipo_operacion": "compra" | "venta",
        "items": [
            {
                "codigo": "...",
                "nombre": "Jabón Líquido Antibacterial",
                "presentacion_sugerida": "Galón 3.8L",
                "cantidad": 5.0,
                "costo_unitario": 25000.0,
                "numero_lote": "LOT-2026-01",
                "fecha_vencimiento": "2027-10-30"
            }
        ],
        "observaciones": "..."
    }
    """
    client = get_openai_client()
    model = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')
    
    prep = encode_file_for_openai(file_bytes, filename)
    
    prompt_instrucciones = f"""
Eres un asistente experto en contabilidad, logística e inventarios químicos y de aseo (sistema Andiaseo).
Analiza el documento adjunto que corresponde a una factura o remisión de {tipo_operacion.upper()}.

Debes extraer los datos y responder OBLIGATORIAMENTE en formato JSON con la siguiente estructura exacta:
{{
    "numero_factura": "cadena con el número o código de factura/remisión (o 'FAC-S/N' si no hay)",
    "fecha": "YYYY-MM-DD (fecha del documento o hoy si no se identifica)",
    "tercero": "Nombre del proveedor o cliente",
    "tipo_operacion": "{tipo_operacion}",
    "items": [
        {{
            "codigo": "código o referencia del producto (o dejar vacío si no se especifica)",
            "nombre": "nombre claro del producto químico o insumo",
            "presentacion_sugerida": "ej: Galón 3.8L, Garrafa 20L, Frasco 500ml, Litros, Kilos, Unidades",
            "cantidad": 1.0,
            "costo_unitario": 0.0,
            "numero_lote": "número de lote si viene especificado, sino cadena vacía",
            "fecha_vencimiento": "YYYY-MM-DD si viene en el documento, sino cadena vacía"
        }}
    ],
    "observaciones": "resumen breve de la factura o notas de extracción"
}}

Reglas estrictas:
1. Extrae únicamente las cantidades numéricas reales (enteros o decimales).
2. Si el documento es una imagen o texto y no logras identificar el lote o vencimiento, deja esos campos como cadenas vacías "".
3. Limpia nombres de productos eliminando códigos tributarios innecesarios.
4. Responde ÚNICAMENTE el JSON, sin bloques markdown adicionales ni texto previo.
"""

    messages = [
        {"role": "system", "content": prompt_instrucciones}
    ]

    if prep["type"] == "image":
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": f"Por favor procesa esta factura/documento de {tipo_operacion}:"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": prep["url"],
                        "detail": "high"
                    }
                }
            ]
        })
    elif prep["type"] == "text":
        messages.append({
            "role": "user",
            "content": f"Por favor procesa el siguiente contenido textual de la factura de {tipo_operacion}:\n\n{prep['content']}"
        })
    else:
        # En caso de PDF escaneado sin texto seleccionable
        # Intentamos enviarlo como advertencia o sugerencia de imagen
        raise ValueError("El archivo PDF parece estar escaneado y no contiene texto seleccionable directo. Por favor toma una foto o captura de pantalla (PNG/JPG) de la factura para procesarla con visión.")

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.1
    )

    raw_text = response.choices[0].message.content
    try:
        data = json.loads(raw_text)
        return data
    except Exception as e:
        raise ValueError(f"No se pudo decodificar la respuesta JSON de OpenAI: {str(e)} -> Respuesta: {raw_text}")

