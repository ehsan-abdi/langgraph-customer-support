import sys
import os

sys.path.append(os.path.dirname(__file__))

from src.graph.workflow import build_graph

def main():
    print("Building graph...")
    app = build_graph()
    
    print("Generating Graph Image...")
    try:
        # draw_png() is LangGraph's native graphviz-based image generator
        img_bytes = app.get_graph().draw_png()
        output_path = os.path.join(os.path.dirname(__file__), "langgraph_diagram.png")
        
        with open(output_path, "wb") as f:
            f.write(img_bytes)
            
        print(f"Successfully saved diagram to {output_path}")
    except Exception as e:
        print(f"Failed to generate diagram: {e}")

if __name__ == "__main__":
    main()
