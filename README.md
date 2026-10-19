# tomato-bonovi-info

Provjera stanja Tomato **bonova** (prepaid) bez mobilne aplikacije.

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

## Izvori

- https://www.tomato.com.hr/cesta-pitanja/racun-na-bonove
- https://www.tomato.com.hr/cesta-pitanja/racun-i-potrosnja
- https://www.tomato.com.hr/cesta-pitanja/moj-tomato
- https://moj.tomato.com.hr/ (ugašen portal)
- https://kompare.hr/savjetnik/kako-provjeriti-stanje-racuna/ (treća strana)
