"""Les configurations publiées et le contrat du serveur.

    python -m unittest discover -s tests -v

Chaque fichier de configs/ est lu comme le lirait son client, puis sert à une vraie poignée de
main MCP (initialize, tools/list) contre le faux serveur : sans clé on ne voit que sign_up, avec
une clé on voit les outils de la clé.
"""
import hashlib
import json
import re
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from faux_mcp import CLE_AGENT, CLE_HUMAIN, CLES, MANIFESTE, FauxMcp, outils_visibles  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
CONFIGS = json.loads((RACINE / "configs" / "index.json").read_text(encoding="utf-8"))["configurations"]
ADRESSE = MANIFESTE["endpoint"]


def lire(config):
    """Le contenu d'un fichier de configuration : (adresse, en-têtes) une fois la clé résolue."""
    texte = (RACINE / "configs" / config["fichier"]).read_text(encoding="utf-8")
    if config["format"] == "toml":
        try:
            import tomllib
        except ImportError:  # Python 3.9 et 3.10 : lecture minimale
            valeurs = dict(re.findall(r'^(\w+)\s*=\s*"([^"]*)"\s*$', texte, re.M))
        else:
            (valeurs,) = tomllib.loads(texte)["mcp_servers"].values()
        entetes = {"Authorization": "Bearer ${%s}" % valeurs["bearer_token_env_var"]} if "bearer_token_env_var" in valeurs else {}
        return valeurs["url"], entetes
    document = json.loads(texte)
    (serveur,) = document[config["racine"]].values()
    adresse = serveur.get("url") or serveur.get("serverUrl") or serveur.get("httpUrl")
    return adresse, dict(serveur.get("headers", {}))


def resoudre(entetes, cle):
    """Remplace la référence à la clé (variable d'environnement ou saisie) par la clé."""
    return {nom: re.sub(r"\$\{(?:env:|input:)?[\w-]+\}|\$[A-Z_]+", cle, valeur) for nom, valeur in entetes.items()}


def rpc(adresse, entetes, methode, params=None, identifiant=1):
    message = {"jsonrpc": "2.0", "method": methode}
    if identifiant is not None:
        message["id"] = identifiant
    if params is not None:
        message["params"] = params
    requete = urllib.request.Request(
        adresse, data=json.dumps(message).encode("utf-8"), method="POST",
        headers=dict(entetes, **{"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}))
    with urllib.request.urlopen(requete, timeout=10) as reponse:
        corps = reponse.read()
        return (json.loads(corps) if corps else None), reponse.headers


def outils_vus(adresse, entetes):
    """La poignée de main d'un client MCP, puis la liste de ses outils."""
    initialisation, recus = rpc(adresse, entetes, "initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}})
    session = {"Mcp-Session-Id": recus["Mcp-Session-Id"]}
    rpc(adresse, dict(entetes, **session), "notifications/initialized", identifiant=None)
    liste, _ = rpc(adresse, dict(entetes, **session), "tools/list", identifiant=2)
    return initialisation["result"], [outil["name"] for outil in liste["result"]["tools"]]


class Configurations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.faux = FauxMcp().demarrer()
        cls.addClassCleanup(cls.faux.arreter)

    def test_chaque_configuration_vise_la_bonne_adresse(self):
        self.assertGreaterEqual(len(CONFIGS), 2)
        for config in CONFIGS:
            with self.subTest(config["fichier"]):
                adresse, entetes = lire(config)
                self.assertEqual(adresse, ADRESSE)
                if config["cle"]:
                    self.assertEqual(list(entetes), ["Authorization"])
                    self.assertTrue(entetes["Authorization"].startswith("Bearer "))
                else:
                    self.assertEqual(entetes, {})

    def test_aucune_cle_n_est_ecrite_dans_le_depot(self):
        for chemin in RACINE.rglob("*"):
            if chemin.is_file() and "tests" not in chemin.relative_to(RACINE).parts and chemin.suffix != ".pyc":
                texte = chemin.read_text(encoding="utf-8")
                self.assertIsNone(re.search(r"sak_[A-Za-z0-9]{6,}", texte), chemin.name)

    def test_sans_cle_on_ne_voit_que_l_inscription(self):
        for config in (c for c in CONFIGS if not c["cle"]):
            with self.subTest(config["fichier"]):
                _, entetes = lire(config)
                initialisation, outils = outils_vus(self.faux.url, entetes)
                self.assertEqual(outils, ["sign_up"])
                self.assertEqual(initialisation["serverInfo"]["name"], "subagent")
                self.assertNotIn("Authorization", self.faux.appels[-1]["entetes"])

    def test_avec_la_cle_on_voit_les_outils_de_la_cle(self):
        attendus = [outil["name"] for outil in outils_visibles(CLES[CLE_AGENT])]
        self.assertNotIn("sign_up", attendus)
        self.assertNotIn("approve_message", attendus)  # la clé d'un agent ne porte pas approve
        self.assertIn("send_email", attendus)
        for config in (c for c in CONFIGS if c["cle"]):
            with self.subTest(config["fichier"]):
                _, entetes = lire(config)
                _, outils = outils_vus(self.faux.url, resoudre(entetes, CLE_AGENT))
                self.assertEqual(outils, attendus)
                self.assertEqual(self.faux.appels[-1]["entetes"]["Authorization"], "Bearer " + CLE_AGENT)

    def test_la_cle_d_un_humain_ouvre_la_validation(self):
        _, outils = outils_vus(self.faux.url, {"Authorization": "Bearer " + CLE_HUMAIN})
        self.assertIn("approve_message", outils)

    def test_une_cle_non_resolue_est_refusee_sans_retomber_sur_l_acces_sans_cle(self):
        # Ce qu'un client envoie quand la variable SUBAGENT_KEY n'existe pas : le texte tel quel, ou rien après « Bearer ».
        for valeur in ("Bearer ${SUBAGENT_KEY}", "Bearer ", "Bearer sak_inconnue"):
            with self.subTest(valeur):
                with self.assertRaises(urllib.error.HTTPError) as refus:
                    outils_vus(self.faux.url, {"Authorization": valeur})
                self.assertEqual(refus.exception.code, 401)
                self.assertEqual(json.loads(refus.exception.read())["error"]["code"], "unauthorized")


class Contrat(unittest.TestCase):
    def test_le_manifeste_couvre_le_registre(self):
        outils = MANIFESTE["tools"]
        self.assertEqual(len(outils), 67)
        self.assertEqual(len({outil["name"] for outil in outils}), len(outils))
        self.assertEqual([o["name"] for o in outils if o["x-subagent"]["sans_cle"]], ["sign_up"])
        for outil in outils:
            with self.subTest(outil["name"]):
                self.assertEqual(outil["inputSchema"]["type"], "object")
                self.assertIs(outil["inputSchema"]["additionalProperties"], False)
                self.assertEqual(outil["outputSchema"]["type"], "object")
                self.assertTrue(outil["title"] and outil["description"])
                self.assertIsInstance(outil["annotations"]["readOnlyHint"], bool)

    def test_l_empreinte_du_manifeste_est_celle_de_ses_outils(self):
        canonique = json.dumps(MANIFESTE["tools"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(MANIFESTE["digest"], "sha256:" + hashlib.sha256(canonique.encode("utf-8")).hexdigest())

    def test_server_json(self):
        serveur = json.loads((RACINE / "server.json").read_text(encoding="utf-8"))
        self.assertRegex(serveur["name"], r"^[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+$")
        self.assertLessEqual(len(serveur["description"]), 100)
        (distant,) = serveur["remotes"]
        self.assertEqual((distant["type"], distant["url"]), ("streamable-http", ADRESSE))
        (entete,) = distant["headers"]
        self.assertEqual(entete["name"], "Authorization")
        self.assertFalse(entete["isRequired"])  # sans clé, sign_up reste ouvert
        self.assertTrue(entete["isSecret"])


if __name__ == "__main__":
    unittest.main()
