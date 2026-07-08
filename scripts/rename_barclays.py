import os
import glob
import re
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CONFLUENCE_DIR = os.path.join(BASE_DIR, "data", "confluence_raw")

def replace_bank_name():
    filepaths = glob.glob(os.path.join(CONFLUENCE_DIR, "*.md"))
    logging.info(f"Checking {len(filepaths)} files for 'Barclays' replacements...")
    
    files_modified = 0
    
    for filepath in filepaths:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        original_content = content
        
        # We need to be careful with URLs vs Text.
        # 1. Exact case matches
        content = content.replace("Barclays", "Aura Bank")
        content = content.replace("BARCLAYS", "AURA BANK")
        
        # 2. Lowercase usually appears in URLs or email addresses
        content = content.replace("barclays", "aurabank")
        
        # 3. Handle possessives (Barclays's or Barclays')
        content = content.replace("Aura Bank'", "Aura Bank's")
        content = content.replace("Aura Bank's's", "Aura Bank's") # Fix double possessive
        
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            files_modified += 1
            
    logging.info(f"Successfully modified {files_modified} files to replace 'Barclays' with 'Aura Bank'.")

if __name__ == "__main__":
    replace_bank_name()
