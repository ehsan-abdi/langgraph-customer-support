import os
import re

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "confluence_raw")

# Patterns indicating the start of boilerplate footer sections
TRUNCATE_PATTERNS = [
    re.compile(r"^##\s+Related\s*$", re.IGNORECASE),
    re.compile(r"^##\s+Contact Us\s*$", re.IGNORECASE),
    re.compile(r"^##\s+Find more help here\s*$", re.IGNORECASE),
    re.compile(r"^###\s+Related\s*$", re.IGNORECASE),
    re.compile(r"^###\s+Contact Us\s*$", re.IGNORECASE),
    re.compile(r"^###\s+Find more help here\s*$", re.IGNORECASE),
    re.compile(r"Was this article helpful", re.IGNORECASE)
]

def clean_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split frontmatter from body
    # Assumes format:
    # ---
    # title: ...
    # ...
    # ---
    # body
    parts = content.split('---', 2)
    if len(parts) < 3:
        # Not standard format, skip or process as whole
        frontmatter = ""
        body = content
    else:
        frontmatter = "---" + parts[1] + "---\n"
        body = parts[2]

    lines = body.split('\n')
    cleaned_lines = []
    truncated = False

    for line in lines:
        # Check if line matches any truncate pattern
        if any(pattern.match(line.strip()) or pattern.search(line) for pattern in TRUNCATE_PATTERNS):
            truncated = True
            break
        cleaned_lines.append(line)

    if truncated:
        # Reconstruct the file
        cleaned_body = '\n'.join(cleaned_lines).strip()
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(frontmatter + "\n" + cleaned_body + "\n")
        return True
    return False

def main():
    count = 0
    total = 0
    for filename in os.listdir(OUTPUT_DIR):
        if filename.endswith(".md"):
            total += 1
            filepath = os.path.join(OUTPUT_DIR, filename)
            if clean_file(filepath):
                count += 1
    print(f"Cleaned {count} out of {total} files.")

if __name__ == "__main__":
    main()
