# IP statique permanente pour l'oscilloscope (NixOS)

## Besoin

L'oscilloscope Siglent SDS1204X-E est câblé en **Ethernet direct** sur l'interface
`enp0s31f6` et répond à l'IP **10.11.13.220** (`10.11.13.0/24`). Le PC doit avoir une
adresse fixe dans ce sous-réseau (**10.11.13.10/24**) pour dialoguer avec le scope.
Actuellement l'adresse est posée à la main (`sudo ip addr add 10.11.13.10/24 dev enp0s31f6`)
et donc perdue à chaque reboot. Objectif : la rendre **permanente et déclarative** via
`/etc/nixos/configuration.nix`.

---

## État actuel de la config réseau

Dans `/etc/nixos/configuration.nix` :

- **Ligne 52** : `networking.hostName = "nixos";`
- **Lignes 60-67** : NetworkManager est **activé** :

  ```nix
      # Enable networking
      networking.networkmanager = {
        enable = true;
        wifi.powersave = false;  # Désactive powersave WiFi (fix déconnexions)
        plugins = with pkgs; [
          networkmanager-l2tp
          networkmanager-strongswan
        ];
      };
  ```

- **Lignes 854-861** : `networking.firewall` (uniquement des ouvertures de ports
  entrants pour Parsec et KDE Connect ; le pare-feu n'est **pas** désactivé, il tourne
  donc avec sa valeur par défaut = actif, filtrage **entrant** seulement).

### Vérifications faites (aucun conflit à fusionner)

- **Aucun** `networking.interfaces.enp0s31f6` existant → on peut le créer tel quel.
- **Aucun** `networking.networkmanager.unmanaged` existant → on peut le créer tel quel.
- **Aucun** `networking.firewall.enable = false` → pas de surprise côté pare-feu.

> Point clé de cohabitation : comme **NetworkManager est actif**, il faut lui dire de ne
> **pas** gérer `enp0s31f6` (`unmanaged`), sinon NM et la config statique de NixOS se
> disputent l'interface (DHCP intempestif, IP qui saute, etc.).

---

## Snippet Nix à ajouter

> **Indentation** : le fichier indente les attributs de premier niveau à **4 espaces**
> (et les niveaux imbriqués à 6). Le bloc ci-dessous respecte ce style. Coller tel quel.

```nix
    # Oscilloscope Siglent SDS1204X-E en Ethernet direct (IP statique).
    # NetworkManager doit laisser l'interface tranquille (unmanaged), sinon
    # conflit (DHCP/IP qui saute) avec l'adresse statique déclarée ci-dessous.
    networking.interfaces.enp0s31f6.ipv4.addresses = [
      { address = "10.11.13.10"; prefixLength = 24; }
    ];
    networking.networkmanager.unmanaged = [ "enp0s31f6" ];
```

### Où l'insérer

Juste **après** le bloc `networking.networkmanager` (qui se ferme par `};` à la
**ligne 67**), donc **à la ligne 68** (la ligne vide). Contexte cible :

```nix
    networking.networkmanager = {
      enable = true;
      wifi.powersave = false;  # Désactive powersave WiFi (fix déconnexions)
      plugins = with pkgs; [
        networkmanager-l2tp
        networkmanager-strongswan
      ];
    };
    #  <-- ligne 67 = "};" ci-dessus ; INSÉRER LE BLOC ICI (ligne 68)
    # Oscilloscope Siglent SDS1204X-E en Ethernet direct (IP statique).
    # NetworkManager doit laisser l'interface tranquille (unmanaged), sinon
    # conflit (DHCP/IP qui saute) avec l'adresse statique déclarée ci-dessous.
    networking.interfaces.enp0s31f6.ipv4.addresses = [
      { address = "10.11.13.10"; prefixLength = 24; }
    ];
    networking.networkmanager.unmanaged = [ "enp0s31f6" ];

    # Set your time zone.
    time.timeZone = "Europe/Brussels";
```

(Placement choisi pour garder les deux options réseau côte à côte et rendre la
cohabitation NM/statique évidente à la relecture. N'importe quel emplacement de premier
niveau dans l'attribut set fonctionne aussi — Nix s'en moque de l'ordre.)

---

## Procédure d'application

```bash
# 1. Éditer la config (sudo requis : fichier root)
sudo $EDITOR /etc/nixos/configuration.nix
#   -> coller le bloc à la ligne 68 (après le bloc networkmanager)

# 2. Appliquer
sudo nixos-rebuild switch
```

### Vérifications après rebuild

```bash
# L'adresse doit apparaître sur l'interface :
ip -brief addr show enp0s31f6
#   attendu :  enp0s31f6  UP  10.11.13.10/24 ...

# NetworkManager doit considérer l'interface comme non gérée :
nmcli device status | grep enp0s31f6
#   attendu :  enp0s31f6  ethernet  unmanaged  --

# Connectivité avec le scope :
ping -c 3 10.11.13.220

# (optionnel) test du port SCPI brut (5025) :
#   nc -vz 10.11.13.220 5025
```

Si `ping` répond, la liaison est bonne. Le scope écoute généralement le **port 5025**
(socket SCPI brut) et/ou **VXI-11** (RPC, portmapper port 111) selon la lib utilisée
(pyvisa, etc.).

---

## Pièges & notes

### Cohabitation NetworkManager (le point sensible)
- `networking.interfaces.<iface>` configure l'interface via **systemd-networkd /
  scripts NixOS**, pas via NM. Sans `unmanaged`, NM continuerait de piloter
  `enp0s31f6` (tenter du DHCP, etc.) et entrerait en conflit avec l'IP statique.
- `networking.networkmanager.unmanaged = [ "enp0s31f6" ];` retire l'interface du
  périmètre de NM. Les autres interfaces (WiFi, etc.) restent gérées par NM normalement.
- Format accepté pour `unmanaged` : nom d'interface direct (`"enp0s31f6"`) ou forme
  explicite `"interface-name:enp0s31f6"`. Le nom simple suffit.

### Pare-feu : rien à ouvrir
- Le pare-feu NixOS (actif par défaut) ne filtre que le **trafic entrant**.
- La communication avec le scope est initiée **par le PC** (connexions **sortantes**
  vers le scope : SCPI 5025, ou VXI-11 vers 111 + ports RPC). Le trafic sortant et les
  réponses associées (connexions établies) ne sont **pas** bloqués → **aucun port à
  ouvrir**.
- Réserve mineure : si on utilise un jour le **canal d'interruption SRQ** de VXI-11
  (l'instrument ouvre alors une connexion *entrante* vers le PC), il faudrait l'autoriser.
  Cas rare ; l'usage SCPI courant (lecture/écriture de commandes, captures) ne l'utilise
  pas. À traiter seulement si une lib le réclame explicitement.

### Adressage
- Le PC en `.10` et le scope en `.220` sont dans le même `/24` : OK.
- Pas de passerelle/DNS à déclarer : liaison point-à-point isolée, aucun routage vers
  Internet via cette interface.

### Rollback
Si le rebuild casse quelque chose (réseau injoignable, etc.) :

```bash
# Revenir à la génération précédente :
sudo nixos-rebuild switch --rollback

# ou, depuis le menu du bootloader, choisir la génération antérieure au reboot.
```

La modif est purement déclarative et localisée à une interface : le risque est faible
et entièrement réversible.

---

## Résumé express

| Élément | Valeur |
|---|---|
| Interface | `enp0s31f6` |
| IP PC (statique) | `10.11.13.10/24` |
| IP scope | `10.11.13.220` |
| Ligne d'insertion | **68** (après le bloc `networkmanager`, ligne 67 = `};`) |
| Cohabitation | `networkmanager.unmanaged = [ "enp0s31f6" ]` **obligatoire** |
| Pare-feu | rien à ouvrir (trafic sortant) |
| Indentation | 4 espaces (style du fichier) |
</content>
</invoke>
