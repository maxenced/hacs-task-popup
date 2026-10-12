# HA Task Popup

Intégration Home Assistant qui affiche **en plein écran sur la tablette** les tâches à faire
(sortir les poubelles, mettre les chaises sur la table…), avec deux boutons : **Fait** et **Snooze**.

- Popup global : aucune carte à ajouter au dashboard. L'intégration charge elle-même un module JS
  sur toutes les pages de HA.
- Rendu dans le style des pop-ups Bubble Card du dashboard : voile sombre flouté, panneau « verre »
  arrondi, boutons en pilule. Le fond prend la couleur choisie pour la tâche.
- Écran de la tablette piloté par l'intégration officielle **Fully Kiosk Browser** : il s'allume
  quand une tâche apparaît et reste allumé tant qu'elle est affichée.

## Installation

### Avec HACS (dépôt personnalisé)

1. HACS → menu ⋮ → **Dépôts personnalisés**.
2. Dépôt : `https://github.com/maxenced/ha_task_popup`, type : **Intégration** → **Ajouter**.
3. Rechercher **HA Task Popup** dans HACS → **Télécharger**, puis redémarrer Home Assistant.
4. Recharger une fois la page sur la tablette (Fully : *Load start URL*) pour charger le module JS.

### À la main

Copier `custom_components/ha_task_popup/` dans `<config>/custom_components/`, puis redémarrer HA.

Il faut Home Assistant 2025.3 ou plus récent (sous-entrées de configuration).

## Configuration

*Paramètres → Appareils et services → Ajouter une intégration → HA Task Popup.*

### Réglages généraux

| Champ | Rôle |
|---|---|
| Tablettes Fully Kiosk | Appareils de l'intégration `fully_kiosk` où le popup s'affiche et dont l'écran est piloté. |
| Afficher le popup sur | *Les tablettes Fully Kiosk choisies uniquement* (défaut) ou *Tous les navigateurs*. |
| Allumer l'écran de la tablette et le garder allumé | Allume l'écran à l'apparition d'une tâche et met le délai de mise en veille Fully à 0 pendant l'affichage. Le délai d'origine est remis quand plus aucune tâche n'est affichée, et l'écran s'éteint ensuite tout seul. |

Ces réglages se modifient ensuite par **Configurer**.

### Tâches

Sur la page de l'intégration : **Ajouter une tâche**. Chaque tâche se modifie ensuite avec ⋮ → *Reconfigurer*.

Champs communs : nom, message (plusieurs lignes possibles), icône, couleur de fond, mode d'affichage
(uniquement *Plein écran* pour l'instant), durée du snooze, déclencheur.

| Déclencheur | Quand la tâche est active |
|---|---|
| **Simple** | Les jours choisis, à partir de l'heure de départ. Elle reste affichée jusqu'à **Fait**, ou jusqu'à l'heure de fin si vous en mettez une. Une nouvelle occurrence remplace la précédente. |
| **Planning** | Pendant les événements d'une entité `calendar`, avec un filtre optionnel « le titre contient » (sans tenir compte des majuscules). |
| **Détection** | Quand une entité (binary_sensor, input_boolean, n'importe quel état) **passe** à l'état choisi (`on` par défaut). La tâche reste active pendant la durée choisie, puis disparaît même sans acquittement. Un passage depuis `unavailable` ou `unknown` est ignoré. |

**Snooze** : la tâche disparaît pendant la durée choisie, puis revient si sa fenêtre est toujours ouverte.
**Fait** : la tâche reste « faite » jusqu'à la fin de la fenêtre, ou jusqu'à la prochaine occurrence.

Quand plusieurs tâches sont actives, elles s'affichent **l'une après l'autre**, de la plus ancienne à la
plus récente. Un compteur « 1 / 3 » indique la file. Une tâche qui revient d'un snooze passe en fin de file.

## Entités et services

Chaque tâche est un appareil avec :

- un capteur d'état (`sensor.<tâche>_etat`, ou `_state` si HA est en anglais) : `inactive`, `active`, `snoozed` ou `done`, avec les attributs `task_id`,
  `trigger`, `message`, `window_start`, `window_end`, `snoozed_until` ;
- deux boutons, **Fait** et **Snooze**.

Services :

```yaml
action: ha_task_popup.ack
data:
  entity_id: sensor.poubelles_etat   # ou task_id: <identifiant de la sous-entrée>
```

```yaml
action: ha_task_popup.snooze
data:
  entity_id: sensor.poubelles_etat
  minutes: 30                         # optionnel, durée de la tâche par défaut
```

## Reconnaissance de la tablette

Le module JS compare `fully.getDeviceId()` avec l'identifiant de l'appareil Fully Kiosk choisi.
Il faut donc que l'option Fully **Advanced Web Settings → Enable JavaScript Interface** soit
activée (c'est déjà le cas sur la tablette du salon).

Pour tester sur un autre navigateur sans changer la configuration, dans la console du navigateur :

```js
localStorage.setItem("ha_task_popup_show", "1"); // toujours afficher ici
localStorage.setItem("ha_task_popup_show", "0"); // ne jamais afficher ici
localStorage.removeItem("ha_task_popup_show");   // revenir au comportement normal
```

## Développement

```bash
uv venv -p 3.14 .venv
uv pip install -p .venv -r requirements_test.txt
.venv/bin/python -m pytest
```
