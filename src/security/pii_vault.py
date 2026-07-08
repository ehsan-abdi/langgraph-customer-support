import re
import uuid
from typing import Dict

class PIIVault:
    """
    A security middleware layer that intercepts text before it hits the LLM
    and tokenizes sensitive customer information (PII) to preserve privacy.
    The original data is securely cached in memory and can be reconstructed
    if the LLM generates a response referencing the token.
    """
    def __init__(self):
        # Maps secure tokens (e.g., <EMAIL_A1B2C3D4>) to original PII strings
        self.vault: Dict[str, str] = {}
        
    def mask(self, text: str) -> str:
        if not text:
            return text
            
        masked_text = text
        
        def _replace_email(match):
            token = f"<EMAIL_{uuid.uuid4().hex[:8].upper()}>"
            self.vault[token] = match.group()
            return token
            
        masked_text = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', _replace_email, masked_text)
            
        # 2. Mask Bank Account Numbers (8 consecutive digits)
        def _replace_acc(match):
            token = f"<ACCOUNT_{uuid.uuid4().hex[:8].upper()}>"
            self.vault[token] = match.group()
            return token
            
        masked_text = re.sub(r'\b\d{8}\b', _replace_acc, masked_text)
            
        # 3. Mask Sort Codes (XX-XX-XX)
        def _replace_sort(match):
            token = f"<SORT_CODE_{uuid.uuid4().hex[:8].upper()}>"
            self.vault[token] = match.group()
            return token
            
        masked_text = re.sub(r'\b\d{2}-\d{2}-\d{2}\b', _replace_sort, masked_text)
            
        # 4. Mask Phone Numbers (basic UK/US regex e.g. 07712345678 or +447712345678)
        def _replace_phone(match):
            token = f"<PHONE_{uuid.uuid4().hex[:8].upper()}>"
            self.vault[token] = match.group()
            return token
            
        masked_text = re.sub(r'\b(?:\+?44|0)\s?(?:\d\s?){9,10}\b', _replace_phone, masked_text)
            
        return masked_text
        
    def unmask(self, text: str) -> str:
        """
        Restores the tokenized strings back to their original PII 
        for the final payload delivered to the end-user.
        """
        if not text:
            return text
            
        unmasked_text = text
        for token, original in self.vault.items():
            unmasked_text = unmasked_text.replace(token, original)
        return unmasked_text
        
    def clear(self):
        """
        Flushes the memory vault. To be called at the end of each agent execution graph.
        """
        self.vault.clear()
