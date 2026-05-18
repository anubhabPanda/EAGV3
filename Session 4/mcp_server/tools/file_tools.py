"""File reading and writing tools for various formats."""
import os
from pathlib import Path
from typing import Union, Dict, Any
import pandas as pd
from PIL import Image
import base64
from io import BytesIO


def read_local_file(file_path: str) -> Dict[str, Any]:
    """
    Read local files (csv, txt, excel, jpg, jpeg).
    
    Args:
        file_path: Path to the file to read
        
    Returns:
        Dictionary with file content and metadata
    """
    try:
        path = Path(file_path)
        
        if not path.exists():
            return {"error": f"File not found: {file_path}"}
        
        extension = path.suffix.lower()
        
        # Text files
        if extension == '.txt':
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {
                "type": "text",
                "content": content,
                "filename": path.name
            }
        
        # CSV files
        elif extension == '.csv':
            df = pd.read_csv(path)
            return {
                "type": "csv",
                "data": df.to_dict('records'),
                "shape": df.shape,
                "columns": list(df.columns),
                "filename": path.name
            }
        
        # Excel files
        elif extension in ['.xlsx', '.xls']:
            df = pd.read_excel(path)
            return {
                "type": "excel",
                "data": df.to_dict('records'),
                "shape": df.shape,
                "columns": list(df.columns),
                "filename": path.name
            }
        
        # Image files
        elif extension in ['.jpg', '.jpeg', '.png']:
            img = Image.open(path)
            buffered = BytesIO()
            img.save(buffered, format=img.format or 'JPEG')
            img_str = base64.b64encode(buffered.getvalue()).decode()
            
            return {
                "type": "image",
                "format": img.format,
                "size": img.size,
                "mode": img.mode,
                "base64": img_str,
                "filename": path.name
            }
        
        else:
            return {"error": f"Unsupported file type: {extension}"}
            
    except Exception as e:
        return {"error": f"Failed to read file: {str(e)}"}


def write_local_file(file_path: str, content: Union[str, Dict, list], file_type: str = "txt") -> Dict[str, str]:
    """
    Write content to local files (csv, txt, excel, jpg, jpeg).
    
    Args:
        file_path: Path where to write the file
        content: Content to write (format depends on file_type)
        file_type: Type of file to write (txt, csv, excel, jpg, jpeg)
        
    Returns:
        Dictionary with status and message
    """
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        if file_type == 'txt':
            with open(path, 'w', encoding='utf-8') as f:
                f.write(str(content))
            return {"status": "success", "message": f"Text file written to {file_path}"}
        
        elif file_type == 'csv':
            if isinstance(content, list):
                df = pd.DataFrame(content)
            elif isinstance(content, dict):
                df = pd.DataFrame([content])
            else:
                return {"error": "CSV content must be a list or dict"}
            
            df.to_csv(path, index=False)
            return {"status": "success", "message": f"CSV file written to {file_path}"}
        
        elif file_type in ['excel', 'xlsx']:
            if isinstance(content, list):
                df = pd.DataFrame(content)
            elif isinstance(content, dict):
                df = pd.DataFrame([content])
            else:
                return {"error": "Excel content must be a list or dict"}
            
            df.to_excel(path, index=False)
            return {"status": "success", "message": f"Excel file written to {file_path}"}
        
        elif file_type in ['jpg', 'jpeg', 'png']:
            # Expect base64 encoded image
            if isinstance(content, str):
                img_data = base64.b64decode(content)
                img = Image.open(BytesIO(img_data))
                img.save(path)
                return {"status": "success", "message": f"Image written to {file_path}"}
            else:
                return {"error": "Image content must be base64 encoded string"}
        
        else:
            return {"error": f"Unsupported file type: {file_type}"}
            
    except Exception as e:
        return {"error": f"Failed to write file: {str(e)}"}
