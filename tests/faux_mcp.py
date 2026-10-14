"""Faux serveur MCP Subagent pour les tests : Streamable HTTP, JSON-RPC, aucune messagerie derrière.

Il parle assez de MCP pour qu'un client s'y branche (initialize, tools/list, tools/call, ping) et
applique la règle d'accès du serveur :
- sans en-tête Authorization : un seul outil, sign_up ;
- avec une clé connue : les outils que ses permissions ouvrent, sans sign_up, et sans verify ni
  attach_human une fois l'espace vérifié ;
- avec un en-tête Authorization qui ne porte pas une clé connue : refus 401. Il ne retombe pas sur
  l'accès sans clé.

Les outils viennent de ../mcp-manifest.json, généré depuis le registre d'opérations du serveur.

Seul, pour essayer la configuration d'un client à la main :
    python tests/faux_mcp.py        # écoute sur http://127.0.0.1:8788/mcp
"""
from __future__ import annotations

import json
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MANIFESTE = json.loads((Path(__file__).parent.parent / "mcp-manifest.json").read_text(encoding="utf-8"))
OUTILS = MANIFESTE["tools"]

CLE_AGENT = "sak_exemple_agent"    # la clé que rend sign_up : send, read, manage_inboxes
CLE_HUMAIN = "sak_exemple_humain"  # la clé d'un humain : les mêmes, plus approve
CLES = {
    CLE_AGENT: {"send", "read", "manage_inboxes"},
    CLE_HUMAIN: {"send", "read", "manage_inboxes", "approve"},
}
VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26"]


def outils_visibles(permissions, verifie=True):
    """Les outils qu'un appelant voit : `permissions` vaut None sans clé."""
    visibles = []
    for outil in OUTILS:
        acces = outil["x-subagent"]
        if permissions is None:
            vu = acces["sans_cle"]
        else:
            vu = (not acces["sans_cle"] and bool(permissions & set(acces["permissions"]))
                  and not (acces["espace"] == "non vérifié" and verifie))
        if vu:
            visibles.append({cle: valeur for cle, valeur in outil.items() if cle != "x-subagent"})
    return visibles


class _Serveur(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass


class FauxMcp:
    def __init__(self, port=0):
        self.appels = []  # chaque requête JSON-RPC reçue : {"methode", "entetes"}
        faux = self

        class Gestionnaire(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _ecrire(self, statut, corps=None, entetes=None):
                octets = b"" if corps is None else json.dumps(corps, ensure_ascii=False).encode("utf-8")
                self.send_response(statut)
                if corps is not None:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(octets)))
                for nom, valeur in (entetes or {}).items():
                    self.send_header(nom, valeur)
                self.end_headers()
                self.wfile.write(octets)

            def do_GET(self):  # pas de flux serveur vers client
                self._ecrire(405, entetes={"Allow": "POST, DELETE"})

            def do_DELETE(self):
                self._ecrire(204)

            def do_POST(self):
                longueur = int(self.headers.get("Content-Length") or 0)
                corps = self.rfile.read(longueur) if longueur else b""
                if self.path.split("?")[0] != "/mcp":
                    return self._ecrire(404, {"error": {"code": "not_found", "message": "Route inconnue."}})
                permissions = None
                porteur = self.headers.get("Authorization")
                if porteur is not None:
                    permissions = CLES.get(porteur[len("Bearer "):]) if porteur.startswith("Bearer ") else None
                    if permissions is None:
                        return self._ecrire(401, {"error": {
                            "code": "unauthorized", "message": "Clé d’API absente, inconnue ou révoquée.",
                            "hint": "Envoyez l’en-tête Authorization: Bearer sak_… avec votre clé. Pas encore de clé ? sign_up en ouvre une, sans clé.",
                        }}, {"WWW-Authenticate": 'Bearer realm="subagent"'})
                try:
                    message = json.loads(corps.decode("utf-8"))
                except ValueError:
                    return self._ecrire(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON illisible."}})
                methode = message.get("method")
                faux.appels.append({"methode": methode, "entetes": dict(self.headers.items())})
                if "id" not in message:  # notification
                    return self._ecrire(202)
                entetes = {}
                if methode == "initialize":
                    demandee = (message.get("params") or {}).get("protocolVersion")
                    resultat = {
                        "protocolVersion": demandee if demandee in VERSIONS else VERSIONS[0],
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "subagent", "title": "Subagent", "version": MANIFESTE["version"]},
                        "instructions": MANIFESTE["instructions"],
                    }
                    entetes["Mcp-Session-Id"] = uuid.uuid4().hex
                elif methode == "ping":
                    resultat = {}
                elif methode == "tools/list":
                    resultat = {"tools": outils_visibles(permissions)}
                elif methode == "tools/call":
                    nom = (message.get("params") or {}).get("name")
                    if nom not in {outil["name"] for outil in outils_visibles(permissions)}:
                        resultat = {"isError": True, "content": [{"type": "text", "text": "Opération inconnue : %s. (code unknown_operation)" % nom}]}
                    else:
                        resultat = {"content": [{"type": "text", "text": "Faux serveur : %s appelé, rien n'est envoyé." % nom}],
                                    "structuredContent": {}}
                else:
                    return self._ecrire(200, {"jsonrpc": "2.0", "id": message["id"],
                                              "error": {"code": -32601, "message": "Méthode inconnue : %s" % methode}})
                self._ecrire(200, {"jsonrpc": "2.0", "id": message["id"], "result": resultat}, entetes)

        self._httpd = _Serveur(("127.0.0.1", port), Gestionnaire)
        self.url = "http://127.0.0.1:%d/mcp" % self._httpd.server_address[1]

    def demarrer(self):
        threading.Thread(target=self._httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        return self

    def arreter(self):
        self._httpd.shutdown()
        self._httpd.server_close()

    def __enter__(self):
        return self.demarrer()

    def __exit__(self, *exc):
        self.arreter()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8788
    faux = FauxMcp(port)
    print("Faux serveur MCP Subagent : %s  (clés : %s, %s ; Ctrl+C pour arrêter)" % (faux.url, CLE_AGENT, CLE_HUMAIN))
    try:
        faux._httpd.serve_forever()
    except KeyboardInterrupt:
        pass
