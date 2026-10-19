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

## Aplikacija

- Prijava ide "preko Tomato mobilne mreže" (bez koda), uz 2FA, korisničkim imenom/lozinkom ili biometrijom.
- Promet kroz app preko Tomato mreže se ne naplaćuje.

## Izvori

- https://www.tomato.com.hr/cesta-pitanja/racun-na-bonove
- https://www.tomato.com.hr/cesta-pitanja/racun-i-potrosnja
- https://www.tomato.com.hr/cesta-pitanja/moj-tomato
- https://moj.tomato.com.hr/ (ugašen portal)
- https://kompare.hr/savjetnik/kako-provjeriti-stanje-racuna/ (treća strana)
