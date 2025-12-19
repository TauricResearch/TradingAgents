from langchain_core.tools import tool
from typing import Annotated
from pathlib import Path
import glob
import os

try:
    import PyPDF2
    PDF_AVAILABLE = True
    PDF_LIB = "PyPDF2"
except ImportError:
    try:
        import pypdf
        PDF_AVAILABLE = True
        PDF_LIB = "pypdf"
    except ImportError:
        PDF_AVAILABLE = False
        PDF_LIB = None


@tool
def get_seeking_alpha_pdfs(
    ticker: Annotated[str, "ticker symbol or stock name"],
    base_dir: Annotated[str, "base directory containing stock folders"] = "/",
) -> str:
    """
    Retrieve and extract text content from PDF files in the local directory.
    Looks for PDF files in {base_dir}/{ticker}/*.pdf
    
    Args:
        ticker (str): Ticker symbol or stock name (used as folder name)
        base_dir (str): Base directory path containing stock folders (default: "/")
    
    Returns:
        str: Extracted text content from all PDF files found
    """
    if not PDF_AVAILABLE:
        return "Error: PyPDF2 or pypdf library is not installed. Please install it with: pip install PyPDF2 or pip install pypdf"
    
    # Construct the path pattern
    pdf_pattern = os.path.join(base_dir, ticker, "*.pdf")
    pdf_files = glob.glob(pdf_pattern)
    
    if not pdf_files:
        return f"No PDF files found in {os.path.join(base_dir, ticker)}/"
    
    all_text = []
    
    for pdf_path in sorted(pdf_files):
        try:
            with open(pdf_path, 'rb') as file:
                if PDF_LIB == "PyPDF2":
                    pdf_reader = PyPDF2.PdfReader(file)
                elif PDF_LIB == "pypdf":
                    import pypdf
                    pdf_reader = pypdf.PdfReader(file)
                else:
                    all_text.append(f"Error: No PDF library available for {pdf_path}\n")
                    continue
                
                pdf_text = []
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    pdf_text.append(page.extract_text())
                text_content = "\n".join(pdf_text)
            
            all_text.append(f"=== File: {os.path.basename(pdf_path)} ===\n{text_content}\n")
            
        except Exception as e:
            all_text.append(f"Error reading {pdf_path}: {str(e)}\n")
    
    if not all_text:
        return f"Found PDF files but could not extract text from any of them in {os.path.join(base_dir, ticker)}/"
    
    return "\n".join(all_text)

