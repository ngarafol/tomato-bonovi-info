# tomato-bonovi-info

Provjera stanja Tomato **bonova** (prepaid) bez mobilne aplikacije.

## Instalacija

### Home Assistant (Marketplace / HACS)

1. HACS -> tri tocke -> *Custom repositories* -> `https://github.com/ngarafol/tomato-bonovi-info`, kategorija **Integration**.
2. Preuzmi **Tomato** i restartaj Home Assistant.
3. *Postavke -> Uredaji i usluge -> Dodaj integraciju -> Tomato*, upisi broj; na mobitel s karticom dolazi SMS s TAN-om.
4. Senzor `sensor.tomato_<broj>` (EUR, `monetary`) s atributima `units` i `msisdn`; osvjezava se svakih 30 min.
5. Akcija `tomato_balance.redeem` (`code` = kod bona) nadoplacuje racun.

Domain je `tomato_balance` jer HA vec ima ugradenu integraciju `tomato` (Tomato router firmware).
Integracija zivi u `custom_components/tomato_balance/`; skripte (`tomato_api.py`, `topup.py`) su neovisne i ostaju za CLI/cron.

## Zašto

- Moj Tomato **web portal je ugašen** ("Moj Tomato portal više nije dostupan!", https://moj.tomato.com.hr/).
- Ostali su USSD i SMS kanali koje Tomato navodi u službenom FAQ-u.

## Provjera stanja (prepaid / bonovi)

| Što | Kako | Izvor |
|---|---|---|
| MB / MIN / SMS iz tarife i opcija | USSD `*113*01#` ili besplatni SMS `?` na **13435** | službeni FAQ |
| Stanje eura na računu | USSD `*101#` | službeni FAQ |
| Dodatni euri na računu | USSD `*108*02#` | službeni FAQ |
| Nadoplata bonom iz ruke | USSD `*103*` + 14-znamenkasti kod s bona + `#` (ne radi izvan HR) | službeni FAQ |
| Nadoplata tuđeg Tomato broja | SMS na **13800**: `14-znamenkasti-kod razmak broj` | službeni FAQ |
| Podrška | **0800 092 092** | tomato.com.hr |
| Govorni automat (nije službeno potvrđeno) | 092 99 88 000 | kompare.hr |

Postpaid (za usporedbu): SMS `TPO` na **13444**, govorni automat **0800 9202**.

## Nadoplata na daljinu (bez SIM-a i bez app-a)

Tomato webshop prodaje bonove online i **iznos sjedne odmah na račun** unesenog
broja; ne treba biti prijavljen ni imati Tomato SIM (`/cesta-pitanja/webshop`).

Web stranica to radi preko javnog API-ja `https://services.tomato.com.hr/vouchers`
(klijent je `client-extensions/vouchers/voucher.js`), koji traži samo statični
`TOMATO-API-KEY` iz tog istog javnog JS-a:

| Metoda | Putanja | Tijelo | Vraća |
|---|---|---|---|
| GET | `/vouchers` | – | fiksni bonovi (4/6/12/16/32 €) + varijabilni, `minValue` 2, `maxValue` 150 |
| POST | `/validate/phone-number` | `{"msisdn":"385921234567"}` | `{"success":bool,"message":...}` |
| POST | `/purchase-voucher` | `{"sapMm":"...","freeEntryValue":<iznos za varijabilni>,"customerData":{"phoneNumber":"+38592...","email":"..."},"companyData":{"name","oib","address","postalCode","city"}}` | `{"redirectLink":...,"paymentGatewayParameters":{...}}` |

Zadnji korak je POST forme na `redirectLink` s parametrima naplate (CorvusPay/A1
gateway, potpisan `hash`-em) — kartica se upisuje u pregledniku. Broj u
`customerData.phoneNumber` je broj koji se nadoplacuje.

`./topup.py` to zamotava:

```sh
./topup.py list                                  # bonovi i promocije
./topup.py check --msisdn 0921234567             # je li broj Tomato
./topup.py buy --msisdn 0921234567 --amount 16 --email ja@example.com --open
```

## Aplikacija

- Prijava ide "preko Tomato mobilne mreže" (bez koda), uz 2FA, korisničkim imenom/lozinkom ili biometrijom.
- Promet kroz app preko Tomato mreže se ne naplaćuje.

Aplikacija koristi Google SMS Retriever pa TAN koji stigne SMS-om upiše sama — zato
kod nikad ne vidiš. WiFi tu ne smeta; mobilna mreža treba samo za carrier prijavu.
Kad `tomato_api.py login` zatraži TAN, app na mobitelu ne sluša, pa poruka samo
sleti na telefon: osoba koja ga ima pročita 6 znamenki (`--tan 123456`).

TAN ide isključivo na broj naveden u zahtjevu i tokeni se vežu na taj broj;
lažiranje MSISDN-a nije opcija — to je upravo provjera koju carrier prijava traži.
Ako si vlasnik broja, a SIM je kod nekoga drugog, legalan put je zamjena/duplikat
SIM-a ili eSIM uz provjeru identiteta kod operatera (0800 092 092).

Ručna analiza aplikacije (mapa endpointa, auth tok, nalazi) namjerno nije u javnom
repou; držim je lokalno.

Automatizacija API-ja gotovo sigurno krši uvjete korištenja — koristiti samo na
vlastitom/obiteljskom broju i svjesno.

### tomato_api.py

```sh
./tomato_api.py login --msisdn 0921234567   # pošalje SMS TAN; ti (ili osoba s mobitelom) upišeš kod
./tomato_api.py status                      # stanje računa + preostale jedinice
./tomato_api.py status --json               # sirovi SDUI odgovor
./tomato_api.py redeem --code 12345678901234
```

- `login` traži **jednokratnu** pomoć: TAN dolazi SMS-om na mobitel s Tomato
  karticom. Nakon toga tokeni (`~/.config/tomato/state.json`, 0600) drže sesiju,
  a `token/refresh` radi s bilo koje mreže.
- Ako `login --msisdn` vrati `invalidCredentials` ("Ovaj broj nije povezan s
  nijednim računom") — broj nema Moj Tomato račun; tada ili registracija, ili
  `login --username <ime> --password` ako račun postoji.
- `status` ispiše stanje i jedinice; `--json` daje sirovi odgovor ako se shema
  promijeni.
- Provjere: `python3 -m unittest test_tomato_api`.
- TAN možeš upisati interaktivno ili ga proslijediti kroz stdin, što je praktično
  kad ti ga netko izdiktira preko telefona:
  `printf '123456\n' | ./tomato_api.py login --msisdn 0921234567`.
- `watch` javlja **samo na prijelazu** ispod praga (alarm se resetira kad stanje
  naraste), pa nema spama:
  ```sh
  ./tomato_api.py watch --below 3            # jedna provjera (za cron)
  ./tomato_api.py watch --below 3 --every 3600
  ```
  Obavijest ide preko macOS `osascript` (ili `notify-send` na Linuxu); `--dry-run`
  samo ispiše naredbu. Cron primjer: `0 9 * * * cd /putanja && ./tomato_api.py watch --below 3`
  (uz `TOMATO_STATE` u okolini ako state nije na defaultnoj putanji).
- `./tomato_api.py balance` ispiše `{"amount": 2.5, "currency": "EUR"}` — za Home
  Assistant i skripte. HA upute (senzor + automacija): [docs/home-assistant.md](docs/home-assistant.md).

## Izvori

- https://www.tomato.com.hr/cesta-pitanja/racun-na-bonove
- https://www.tomato.com.hr/cesta-pitanja/racun-i-potrosnja
- https://www.tomato.com.hr/cesta-pitanja/moj-tomato
- https://moj.tomato.com.hr/ (ugašen portal)
- https://kompare.hr/savjetnik/kako-provjeriti-stanje-racuna/ (treća strana)
