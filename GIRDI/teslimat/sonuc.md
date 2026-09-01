# S12 · Teslimat gerçekliği

**Durum: TEKNİK TARAF HAZIR VE ÖLÇÜLDÜ. Dört kutuya bakmak Damla'da.**
Bu faz bilerek insanda kalıyor — ajanın posta kutusu yok, dört sağlayıcıda
hesabı yok, ve "spam'e düştü mü" sorusunun tek dürüst cevabı kutuya bakmaktır.

## Ölçülen (1 Eyl 2026)

| ne | sonuç |
|---|---|
| Alan adı doğrulaması (Resend) | **verified** — DKIM · SPF MX · SPF TXT üçü de |
| SPF | `v=spf1 include:amazonses.com ~all` |
| DKIM | `resend._domainkey.mail.noseydewdrop.com`, 1024-bit RSA |
| DMARC | `v=DMARC1; p=none; rua=mailto:<Damla'nin adresi>` |
| Hizalama | Gönderen `news@mail.noseydewdrop.com`; SPF ve DKIM aynı alt alanda → DMARC hizalı |
| Apex sitesi | Etkilenmedi, MX apex'e konmadı |
| `List-Unsubscribe` | Her mailde var, token'lı |
| `List-Unsubscribe-Post` | **Yok, bilerek** — sayfa statik, POST'a 405 döner |
| text + html | İkisi de var (tek parçalı mail spam sinyali) |
| Gövde | 648 karakter · BÜYÜK HARF %4,2 · 0 ünlem · 0 spam tetik kelimesi |
| Gerçek gönderim | Resend `3c5f3815-6a07-4341-b71a-1ac30bad66fa` → **delivered** |

## Bilinen zayıflık — gizlenmiyor

**Alan adı yeni.** `mail.noseydewdrop.com` 1 Eyl 2026'da doğrulandı, gönderim
itibarı sıfırdan başlıyor. Teknik kurulum kusursuz olsa bile yeni alan adlarının
ilk haftalarda Promosyonlar'a düşmesi normaldir. Kart Promosyonlar'ı kabul
ediyor, spam'i etmiyor.

## Damla'nın yapacağı — tek iş

Dört adrese kaydol (`https://nosey-dewdrop.github.io/sightstone/`), ertesi
sabahki koşuyu bekle, dört kutuya bak:

- [ ] Gmail — gelen kutusu / promosyonlar / **spam**
- [ ] Outlook — gelen kutusu / **spam**
- [ ] Yandex — gelen kutusu / **spam**
- [ ] Üniversite (bilkent) — gelen kutusu / **spam**

Ekran görüntülerini bu klasöre koy. **Biri spam'e düşerse koşu DURUR** ve
hangi fazın kartı yanlıştı diye sorulur — sayı "düzeltmek için" değiştirilmez.

## Neden dördü de aynı anda denenebilir

Onay maili günlük koşuya biniyor, yani dört kayıt aynı gece yapılırsa dördü de
ertesi sabah tek koşuda gider. Kota bugün 90/gün, dört mail sorun değil.
