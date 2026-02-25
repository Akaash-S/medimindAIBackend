from pypdf import PdfReader
import io

class OCRService:
    @staticmethod
    def extract_text(file_bytes: bytes, file_name: str) -> str:
        """
        Extract text from medical reports. 
        Supports PDF and plain text.
        """
        if file_name.lower().endswith(".pdf"):
            try:
                reader = PdfReader(io.BytesIO(file_bytes))
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                return text.strip()
            except Exception as e:
                print(f"PDF extraction error: {e}")
                return ""
        
        try:
            return file_bytes.decode("utf-8")
        except:
            return ""

ocr_service = OCRService()
