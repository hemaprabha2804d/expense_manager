import docx

def read_docx(file_path):
    doc = docx.Document(file_path)
    full_text = []
    for para in doc.paragraphs:
        full_text.append(para.text)
    return '\n'.join(full_text)

try:
    print(read_docx(r'c:\hema\OneDrive\Desktop\thread ctt.docx'))
except Exception as e:
    print(f"Error: {e}")
