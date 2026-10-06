"""Statut d'acquisition et attente de déclenchement (SDS1204X-E).

Fondation de la future **capture sous condition** : ce module fournit le socle
minimal — lire le statut (``SAST?``), lire/effacer le registre d'état interne
(``INR?``) et attendre un déclenchement par sondage. La logique de conditions
elle-même (capturer si tel seuil/motif) n'est pas ici : c'est la brique
suivante, une fois ce socle validé sur matériel.

Approche retenue : **sondage** (``INR?`` en boucle courte), pas la commande
bloquante ``WAIT`` du firmware — plus prudent sur ce matériel (cf. l'incident
``MSIZ`` documenté dans ``docs/scpi-reference.md``) et cohérent avec le reste
du code (write/query courts, jamais de commande qui bloque le firmware).
"""

from __future__ import annotations

import time


def parse_sample_status(response: str) -> str:
    """Extrait le statut de ``SAST <status>`` (ex. ``"SAST Trig'd"`` -> ``"trig'd"``)."""
    token = response.split(maxsplit=1)[-1] if response.split() else response
    return token.strip().lower()


def parse_inr(response: str) -> int:
    """Extrait la valeur de ``INR <value>`` (ex. ``"INR 8913"`` -> ``8913``)."""
    token = response.split()[-1] if response.split() else response
    return int(token)


def triggered(inr_value: int) -> bool:
    """Bit 0 du registre INR : un déclenchement a eu lieu depuis la dernière lecture."""
    return bool(inr_value & 1)


def sample_status(scope) -> str:
    """Lit le statut d'acquisition (SCPI ``SAST?``)."""
    return parse_sample_status(scope.query("SAST?"))


def read_inr(scope) -> int:
    """Lit le registre d'état interne (SCPI ``INR?``). Attention : la lecture l'efface."""
    return parse_inr(scope.query("INR?"))


def wait_for_trigger(
    scope,
    *,
    timeout_s: float = 10.0,
    poll_s: float = 0.05,
    clock=time.monotonic,
    sleep=time.sleep,
) -> bool:
    """Attend qu'un trigger se déclenche, par sondage de ``INR?``.

    **À appeler après avoir armé l'acquisition** (``control.set_trigger_mode(scope,
    "SINGLE")`` puis ``control.run(scope)``). Sonde ``INR?`` jusqu'à ce que le bit 0
    (déclenché depuis la dernière lecture) passe à 1, ou que ``timeout_s`` soit
    dépassé.

    **Important (constaté sur matériel, SDS1204X-E)** : cette fonction ne fait
    volontairement **aucune** lecture de purge après l'armement. Sur un signal
    rapide/propre, le trigger peut déjà être latché dès le tout premier ``INR?``
    (observé : signal carré ~1 kHz déclenché en <1 ms) — et le mode ``SINGLE`` ne
    se ré-arme pas tout seul après un trigger. Une purge faite ici consommerait
    ce déclenchement réel au lieu d'un résidu, et ferait timeout à tort même sur
    un signal parfaitement valide. Si une purge d'un résidu d'un **précédent**
    armement est nécessaire, elle doit se faire par l'appelant, **avant**
    ``control.run(scope)`` (donc avant l'armement), pas ici.

    ``clock``/``sleep`` sont injectables (tests sans vraie temporisation).
    Retourne ``True`` si déclenché, ``False`` en cas de timeout.
    """
    deadline = clock() + timeout_s
    while clock() < deadline:
        if triggered(read_inr(scope)):
            return True
        sleep(poll_s)
    return False
