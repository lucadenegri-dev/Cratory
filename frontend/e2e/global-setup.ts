/* La suite gira su un DB che parte vuoto: senza questo, il SetupGate
   reindirizzerebbe ogni rotta dello smoke test al wizard. Il flag si scrive
   con l'API vera, non con una scorciatoia. */
export default async function globalSetup() {
  const res = await fetch("http://127.0.0.1:8211/api/setup/state", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ completed: true }),
  });
  if (!res.ok) throw new Error(`setup state non impostato: HTTP ${res.status}`);
}
