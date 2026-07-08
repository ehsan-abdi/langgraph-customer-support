import { JSDOM, VirtualConsole } from 'jsdom';

(async () => {
  const virtualConsole = new VirtualConsole();
  
  virtualConsole.on("log", (message) => {
    console.log("BROWSER_LOG:", message);
  });
  
  virtualConsole.on("jsdomError", (error) => {
    console.error("JSDOM_ERROR:", error.message, error.stack);
  });
  
  virtualConsole.on("error", (message, ...args) => {
    console.error("BROWSER_ERROR:", message, ...args);
  });
  
  console.log("Loading page in JSDOM...");
  try {
    const dom = await JSDOM.fromURL("http://localhost:5173/", {
      runScripts: "dangerously",
      resources: "usable",
      virtualConsole
    });
    
    // Wait for JS to execute
    await new Promise(r => setTimeout(r, 2000));
    console.log("Done.");
  } catch (err) {
    console.error("Failed to load JSDOM:", err);
  }
})();
