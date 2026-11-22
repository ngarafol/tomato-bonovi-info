# Home Assistant integracija

Cilj: `sensor.tomato_stanje` u HA + automacija koja javi kad stanje padne pod prag.
Skripta ostaje jedini "integrator" — nema custom komponente.

## 1. Priprema na HA hostu

Skripta mora biti na istom hostu na kojem se izvršava (`python3` mora postojati;
radi s 3.8+). Za HA OS / Supervised:

```sh
mkdir -p /config/tomato
cp tomato_api.py /config/tomato/
chmod +x /config/tomato/tomato_api.py

# login napravi bilo gdje (npr. na laptopu), pa prekopiraj state file:
scp ~/.config/tomato/state.json root@homeassistant:/config/tomato/state.json
```

Provjeri da radi iz HA konteksta:

```sh
python3 /config/tomato/tomato_api.py balance      # -> {"amount": 2.5, "currency": "EUR"}
```

`state.json` sadrži refresh token → drži ga izvan git-a i backupa koji ide u oblak.
Ako HA ne smije izlaziti na `webauth.tomato.com.hr`, preskoči na varijantu 3.

## 2. Senzor (varijanta 1 — preporučeno)

`configuration.yaml`:

```yaml
command_line:
  - sensor:
      name: Tomato stanje
      unique_id: tomato_balance
      command: "python3 /config/tomato/tomato_api.py balance"
      value_template: "{{ value_json.amount }}"
      unit_of_measurement: "EUR"
      device_class: monetary
      state_class: total
      scan_interval: 1800
      command_timeout: 60
```

- `command_line` ide **na vrh** `configuration.yaml` (od 2022.12 nije pod `sensor:`).
- `scan_interval: 1800` = svakih 30 min; default je 30 s, što je prečesto.
- `command_timeout: 60` jer skripta na 401 radi refresh + ponovni poziv (default 15 s
  može biti tijesno).
- Naredba se izvršava u kontekstu HA kontejnera s radnim direktorijem `/config`
  (zato apsolutna putanja i vrijedi; `python3` tamo postoji, skripta je stdlib-only).
- **Ako skripta izađe s ne-0** (mreža, istekao token), HA **ne** mijenja stanje
  senzora — ostaje zadnja vrijednost, a greška ide u log. Ako želiš da takav
  senzor postane `unavailable`, dodaj u **isti** `command_line:` popis još i
  binary sensor:

  ```yaml
  - binary_sensor:
      name: Tomato API dostupan
      unique_id: tomato_api_ok
      command: "python3 /config/tomato/tomato_api.py balance"
      value_template: "{{ 'on' if value_json.amount is defined else 'off' }}"
      device_class: connectivity
      scan_interval: 1800
      command_timeout: 60
  ```

  i na senzor stavi `availability: "{{ is_state('binary_sensor.tomato_api_dostupan', 'on') }}"`.
  (Jednostavnija varijanta — samo senzor — sasvim je u redu ako povremeno pogledaš log.)
- Token se osvježava sam (`token/refresh` na 401), pa nema dodatnog održavanja.

## 3. Varijanta 2 — guranje stanja preko HA REST API-ja

Kad ne želiš da HA izvršava skriptu (npr. state file i mreža su na drugom stroju).
Na tom stroju u `crontab`:

```sh
*/30 * * * * /opt/tomato/tomato_api.py balance | jq -c '{state: .amount, attributes: {unit_of_measurement: "EUR", currency: .currency, friendly_name: "Tomato stanje"}}' | curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" --data-binary @- http://homeassistant.local:8123/api/states/sensor.tomato_stanje
```

Token: HA → Profil → Sigurnost → Dugoročni pristupni tokeni. Senzor se stvara sam
prvim POST-om; `state_class`/`device_class` se ne mogu postaviti REST-om — dodaj ih
u `customize.yaml` ako ti treba statistika.

## 4. Automacija (umjesto `watch`)

```yaml
automation:
  - alias: "Tomato: nisko stanje"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.tomato_stanje
        below: 3
        for: "00:05:00"
    actions:
      - action: notify.mobile_app_tvoj_telefon
        data:
          title: "Tomato — nisko stanje"
          message: >-
            Stanje je {{ states('sensor.tomato_stanje') }} €
            (prag 3 €). Nadoplati: tomato.com.hr/bonovi
```

`for:` spriječi da tranzicija tijekom restarta HA dvaput oglasi alarm. `watch`
naredba u skripti tada nije potrebna — HA preuzima notifikacije.

## 5. Opcionalno: nadoplata iz HA

`topup.py buy` vraća `payment.html` s potpisanom formom — plaćanje karticom svejedno
ide u pregledniku, pa nema smisla zvati ga iz automacije. Ako imaš kod bona
(kupljen unaprijed), `redeem` može ići preko `shell_command`:

```yaml
shell_command:
  tomato_redeem: "python3 /config/tomato/tomato_api.py redeem --code {{ code }}"
```

…ali to je akcija s novcem; radije je pozovi ručno iz Developer Tools nego da je
vežeš na automaciju.
