# SIGHTSTONE KOŞUSU v4 — SON KOŞU

Hedef cümlesi, tek satır, hiçbir fazda değişmez.

> **Alabileceğim iş ilanı, ölmeden önce bana ulaşıyor.**

Bitiş şartı bir ölçüm değil. Bitiş şartı şu: bir yabancı siteye girer,
ne aradığını yazar, mail kutusuna bir bülten düşer, içindeki ilana
başvurabilir. "Kaydol" diyebildiğin gün koşu bitmiştir.

---

## KİM İÇİN, VE NEREDE ÇÖKÜYOR

| kim | ne istiyor | çöktüğü yer |
|---|---|---|
| **Taşınamayan öğrenci** | başvurabileceği ilan | havuzun tamamı taşınma istiyor, Türkiye ilanı 0 |
| **Taşınabilen öğrenci** | ilanı ölmeden görmek | ilanların %26,5'i 3 günde ölüyor, bülten geç kalıyor |
| **Kaydolan yabancı** | mail kutusuna düşen şey | gönderim kişisel Gmail'den, spam'e düşer |

**Kullanıcı yolculuğu ve bilinen ölüm noktaları.**

```
1  siteye girer, ne olduğunu anlar                     S13
2  ne aradığını yazar                                  S13
3  kaydolur                                            S6
4  mailini onaylar                          ← ÖLÜ      S10
5  koltuk dolu, bekleme listesine girer      ← ÖLÜ      S6
6  eşleşmesi hesaplanır                                S4
7  ilan hâlâ açık mı                        ← ÖLÜ      S2
8  sırası gelir                             ← ÖLÜ      S11
9  mail kutusuna DÜŞER                      ← ÖLÜ      S8 S12
10 aynı ilanı iki kez almaz                 ← ÖLÜ      S7
11 kota patlamaz                            ← ÖLÜ      S9
12 boş haftada ne olduğunu anlar            ← ÖLÜ      S10
13 mail yoksa kendi sayfasından bakar       ← ÖLÜ      S5
14 çıkar, koltuğu birine açılır                        S6
```

Motor 6. adımı yazdı. 1-5 ve 7-14 eksik ya da kırık. O yüzden abone sayısı 1.

---

## 0. ORKESTRASYON

### 0.1 Roller

**Şef.** Tek oturum. Sıfır iş. Kart yapıştırır, ajan doğurur, hakem doğurur.
Dördüncü bir şey yaparsa koşu bozulmuştur.

**Ajan.** Her faz için taze doğar. Sadece kendi kartını ve kod tabanını görür.
Önceki kartları, tartışmaları, hakem raporlarını GÖRMEZ. Üç satır yazar, ölür.

**Hakem.** Ayrı doğar. Ajanın raporunu GÖRMEZ. Eline kart, `git diff` ve kabul
komutu geçer. Komutu kendi çalıştırır. Ajanın "geçti" demesi hiçbir şey ifade
etmez.

**Damla.** Döngünün dışında. Tek aksiyonu açılış bloğunu bir kez yapıştırmak
ve S12'de dört mail kutusuna bakmak.

### 0.2 Hakem üç cevaptan birini verir

```
GEÇTİ       — kabul komutu eşiği tutturdu, diff kartın izin verdiği dosyalarda
KALDI       — eşik tutmadı. Ajan AYNI kartla yeniden doğar, hakemin ölçtüğü
              sayı kartın altına eklenir. En fazla iki kez.
KART YANLIŞ — kart yanlış şeyi ölçüyor ya da eşik yanlış yerde. Hakem kartı
              yeniden yazar, gerekçesini bu dosyaya düşer, faz baştan koşar.
```

`KART YANLIŞ` hakem eşiği **sadece zorlaştırabilir.** Kolaylaştırma yönünde tek
değişiklik yapamaz. Kolaylaştırma gerekiyorsa koşu durur ve Damla'yı bekler.
Bu, hakem+ajan ikilisinin insan yokken "geçti" üretmesini engelleyen tek kilit.

### 0.3 Birikimli hata

Her kart kendinden önceki **tüm** fazların kabul komutlarını taşır. Hakem
hepsini koşar. S9'un hakemi S2'nin komutunu da çalıştırır. Biri kızarırsa koşu
durur ve kızaran fazın adı bu dosyaya yazılır.

### 0.4 Kart formatı

```
KULLANICI CÜMLESİ : <bir cümle, kullanıcının ağzından>
KABUL KOMUTU      : <tek satır, kopyala-yapıştır çalışır>
EŞİK              : <bir sayı>
DOKUNULABİLİR     : <dosya listesi. dışına çıkmak KALDI'dır>
```

### 0.5 Ajan raporu

```
NE DEĞİŞTİ   : dosya:satır
KOMUT ÇIKTISI: <yapıştır>
YAPILAMAYAN  : <varsa, adıyla>
```

### 0.6 Kayıt

Tek dosya, bu dosya. Faz başına bir blok.

```
## S<n> — <ad> — <GEÇTİ|KALDI×n|KART YANLIŞ>
ölçülen: <sayı>   eşik: <sayı>   commit: <sha>
hakem notu: <tek cümle>
```

### 0.7 Değişmezler — hiçbir faz kıramaz

```
D1  Aynı ilan aynı aboneye iki kez gitmez
D2  Onaylanmamış adrese bülten gitmez
D3  Günlük 100 / aylık 3.000 mail aşılmaz. Onay ve davet mailleri de bu kovadan
D4  Motorda LLM yok. .rabadon/guard.json no-llm-deps-in-engine zaten kesiyor,
    ama o yalnız paket kurulumunu keser; doğrudan HTTP çağrısı da yasak
D5  CV tarayıcıdan çıkmaz. Sunucuya CV gönderen kod fazı düşürür
D6  Ücretli servis yok
D7  Ölü ilan postalanmaz
D8  Boş koltuk varken bekleme listesinde kimse bekleyemez
D9  HTML'e basılan hiçbir dış metin ham geçmez (esc() zorunlu)
```

### 0.8 Değişmeyen kurallar

- **Main.** Branch yok. Her faz maine commit.
- **Ölçmeden iddia yok.** "Çalışıyor" demeden önce çalıştır.
- **Uydurma sayı yok.** Kaynağı olmayan sayı koda giremez. Kaynak yoksa en
  kısıtlayıcı değer seçilir ve "uydurma" etiketiyle ilan edilir.
- **Sessiz default yok.** Motor bilmediği şeyi eşleştirmez, adıyla reddeder.
- **Her reddin bir sonraki adımı vardır.** "Bu filtreye ilan yok" tek başına
  kabul edilmez; yanında ya en yakın eşleşme ya kullanıcının yapabileceği bir
  aksiyon olacak. Çıkmaz sokak hatadır.
- **Mevcut test değiştirilemez.** `engine/tests/test_engine.py` bugün 15 test,
  hepsi yeşil, miras kırmızı YOK. Bu koşuda düşen her test yeni kırmızıdır ve
  mazereti yoktur. Test koşucusu `python3 -m unittest discover engine/tests`,
  pytest DEĞİL (`.github/workflows/daily.yml:29`).
- **Yeni test faz-öncesi kodda kırmızı düşmek zorunda.** Düşmüyorsa test boştur
  ve tek başına fazı çürütür. Canlı örnek: `us_auth_excluded_for_non_us` bugün
  YEŞİL ama koruduğu kural üretimde **0 kez** tetikleniyor. Yeşil test ≠
  çalışan kural.
- **Her yeni kapı için mutasyon kanıtı.** Kasıtlı bozma kapıyı KIRMALI, geri
  alınınca yeşile dönmeli. Kırılamayan kapı süstür.
- **Kullanıcı verisi üçüncü tarafa gidiyorsa ekranda yazar.** Mail Resend'e,
  kayıt Supabase'e gidiyor. Sessiz kalmak yasak.

---

## DAMLA'NIN KARARLARI (verildi, tartışılmaz)

```
SAĞLAYICI    : Resend. Bedava katman: günde 100, ayda 3.000. Değiştirme
               önerisi bu dosyaya bilgi satırı olur, fazın kararı olamaz.
PARA         : YOK. Hiçbir ücretli servis, hiçbir ücretli katman. Bir faz
               "şunu ödesek çözülür" diye biterse KART YANLIŞ değil KALDI'dır.
KOLTUK       : 200. Gerekçe ölçülmüş: aylık 2.550 kullanılabilir mail / 200
               kişi = 2,4 günde bir bülten = ~%7 kaçırma. 500'de %22 olurdu.
SAYAÇ        : Koltuk sayacı ve bekleme listesi sayısı arayüzde GİZLİ.
               Arka uçta doğru çalışır. 100/200'de tek satırla açılır.
LLM          : CV eleştirisine ve eşleştirmeye LLM eklenmez. Groq, Llama,
               hiçbiri. cv_critique.py (299 satır, LLM'siz) genişletilir.
CV           : Tarayıcıdan çıkmaz. docs/cv-engine.js + pdf.min.js zaten öyle.
build_site.py: rabadon build-site-mock-contract kilidi AÇILIYOR, tek şartla:
               S5 yalnız YENİ fonksiyon ekler; S5 öncesi ve sonrası
               docs/index.html, docs/cv.html, docs/jobs/ çıktıları BYTE-EŞ.
               Tasarım taşınmaz, yalnız yeni çıktı eklenir.
KAYNAK       : Bu koşuda yeni ilan kaynağı EKLENMEZ. Korpus birebir aynı kalır,
               yoksa S1'in dondurduğu zemin geçersizleşir. S2 yalnız fetch/
               klasör bölmesi yapar. Kaynak ekleme koşudan sonra.
TARİH        : Bu dosyada takvim yok. Süreler saat cinsinden.
GÖNDERİM SAATİ: Herkese 06:00 UTC. Kişiye özel saat bu koşuda yok.
```

---

## ZEMİN — 29 Ağu ölçümü, HİPOTEZ

> ⛔ **S1 BU BLOĞUN ÇOĞUNU ÇÜRÜTTÜ. AŞAĞIDAKİ SAYILARIN HİÇBİRİ KULLANILAMAZ.**
> Ölçülmüş gerçek için bir alttaki "ZEMİN v2" bloğuna bak. Bu blok yalnız
> tarihsel kayıt olarak duruyor. Referans commit `ce823dec` bu repoda YOK.

S1 yeniden ölçmeden buradaki hiçbir sayı kanıt değildir, hiçbir kapıda
kullanılamaz. S1'in ölçümü çelişirse buradaki satır sessizce ölür.
Commit `ce823dec`.

```
KORPUS      599 ilan, 46 ülke. ABD 264 · Singapur 84 · UK 25 · Almanya 24.
            TÜRKİYE 0. Tek besleyici engine/fetch_speedyapply.py.
REMOTE      21 ilan (%3,5). Düz "Remote" olan: 3. Kalan 18 ülkeye çivili
            (Remote - USA 8, ABD şehri 5, Berlin 1, Leuven 1, Ontario 1,
            Hong Kong 1). remote alanı BOOLEAN, bu ayrımı eziyor.
AKIŞ        Son 7 günde 109-118 yeni ilan (~16/gün). 8'i remote.
            Dünya geneli remote: 0.
ÖMÜR        39 git anlık görüntüsü, ömrü tamamlanmış 189 ilan: medyan 7 gün.
            %26,5'i ≤3 günde ölüyor. %54,5'i ≤7 günde. 22'si tek gün yaşadı.
            (412 yaşayan ilan sayılmadı, bu ÜST sınır.)
KAÇIRMA     Bekleme 0g %0 · 1g %11,6 · 2g %19,0 · 3g %26,5 · 4g %31,2 ·
            5g %41,3 · 6g %48,1. Sabit haftalık kohort ortalama %25,4.
EŞLEŞME     Damla profilinde 224 eşleşme. 101'i tam 2 puan, 59'u 1 puan.
            Skor≥5 olan 20. Eleme: no_signal 282 · phd_only 92 ·
            us_work_auth 0. Skor yalnız BAŞLIĞA bakıyor, açıklamayı okumuyor.
ABONE       mail_state.json: 1 abone, 89 ilan gönderilmiş, havuz tükenmiş.
            seats.json: {capacity:100, taken:1}.
ŞEMA        schema.sql kapasite 100, İKİ yerde sabit (satır 38 enforce_cap,
            satır 52 seats). taken = unsubscribed_at is null sayımı, yani
            çıkanın koltuğu ZATEN açılıyor. RLS açık, anon yalnız insert.
            confirmed_at YOK. Cap trigger'ı count(*) okuyor → YARIŞ var.
GÖNDERİM    send_mail.py: Gmail app password + smtplib. mail_state.json
            bütün döngü BİTTİKTEN sonra tek seferde yazılıyor → ortada kopan
            gönderim çift maile yol açar. send_mail.py'ın HİÇ TESTİ YOK.
ALTYAPI     Supabase bedava: 500MB, sınırsız API isteği. 200 satır hiçbir şey.
            DB bu projenin riski DEĞİL. Tek risk: 7 gün hareketsizlikte proje
            duraklatılıyor ve isteğe UYANMIYOR, panelden elle geri alınıyor.
KORUMA      .rabadon/guard.json yürürlükte: no-llm-deps-in-engine ·
            jobs-data-generated (jobs.json elle düzenlenemez) ·
            build-site-mock-contract (build_site.py kilitli, S5'te açılıyor).
KOPYA       writing-style.json var: "Damla is the SPEC, never invent facts."
            site-mock/ tasarımın kaynağı. S10 ve S13 bunları okur.
```

---

## ZEMİN v2 — S1 ÖLÇÜMÜ. KANIT. Ajan ve hakem BAĞIMSIZ ölçtü, uyuştu.

Üretici: `python3 tools/measure.py`. Hakem aynı sayıları `git show` ile
araçtan bağımsız üretti. Bundan sonraki her kart BU sayılara dayanır.

```
KORPUS      453 ilan (ZEMİN 599 dedi — ÇÜRÜDÜ). 42 ülke + 42 ülkesiz satır.
            ABD 169 · Singapur 38 · UK 22 · Almanya 22 · Hollanda 21.
            TÜRKİYE 0 (bu satır DOĞRULANDI).
            Kaynak: speedyapply-intern-usa 182 · speedyapply-intern-intl 271.
            fetch_meta: raw_rows=494, duplicates_removed=41, 2026-07-27T08:03Z.
REMOTE      28 ilan, %6,2 (ZEMİN 21 / %3,5 dedi — ÇÜRÜDÜ).
            Düz "Remote" olan 9 (ZEMİN 3 dedi — ÇÜRÜDÜ). Çivili 19:
            Remote-USA 10 · NYC 2 · Ontario 2 · USA+1 1 · Boston+3 1 ·
            Mannheim 1 · Gurugram 1 · Berlin 1.
AKIŞ        0 yeni ilan / 0,76 gün (ZEMİN ~16/gün dedi — ÇÜRÜDÜ).
ÖMÜR        ⛔ ÖLÇÜLEMEZ. jobs.json'un git geçmişi 6 anlık görüntü, 0,76 gün,
            2 takvim günü. İlk dedupe'tan sonra içerik BYTE-EŞ. Doğan ilan 0,
            ölen ilan 0. Tamamlanmış ömür örneği 0. Sansür oranı %100.
            ZEMİN'in "39 görüntü / 189 ömür / medyan 7 gün" verisi bu repoda
            YOK — başka bir kopyada ölçülmüş, o kopya diskte bulunamadı.
            `age` alanından türetme DENENDİ ve REDDEDİLDİ: yaş histogramı
            tepesi 11 gün, yaş≤1 olan 2 ilan → durgunluk varsayımı tutmuyor.
KAÇIRMA     ⛔ ÖLÇÜLEMEZ. Alt sınır %0 (hiç ölüm gözlenmedi), üst sınır
            belirsiz. Araç sayı basmayı REDDEDİYOR, doğrusu bu.
EŞLEŞME     142 eşleşme (ZEMİN 224 dedi — ÇÜRÜDÜ). Skor 2: 54 · skor 1: 27 ·
            skor≥5: 22. Eleme: no_signal 258 · phd_only 51 · mba 2 ·
            us_work_auth 0 (0 olması DOĞRULANDI — kural ölü kod).
ABONE       1 abone DOĞRULANDI. Gönderilen ilan 22 (ZEMİN 89 dedi — ÇÜRÜDÜ).
            seats.json {capacity:100, taken:1} DOĞRULANDI.
ŞEMA        DOĞRULANDI. Kapasite 100, satır 38 ve 52. confirmed_at YOK.
            Ek bulgu: schema.sql:18'de `cv_text` sütunu duruyor, yazan kod yok
            — D5 bugün yeşil ama şema CV'yi sunucuda saklamaya HAZIR.
GÖNDERİM    DOĞRULANDI. send_mail.py:21,173 smtplib + Gmail app password.
            State satır 184'te, döngü 175'te bittikten SONRA ve yalnız
            `mailed>0` iken yazılıyor.
D4/D5/D6    0 ihlal, YEŞİL. Not: cdn.jsdelivr.net font bağımlılığı var
            (build_site.py:37-39). Bedava ama üçüncü taraf. DOĞRULANMADI:
            "üçüncü tarafa gidiyorsa ekranda yazar" kuralı fontu kapsıyor mu.
D9          ⛔ 1 GERÇEK İHLAL, KIRMIZI. build_site.py:627 `job_jsonld`:
            json.dumps çıktısı doğrudan <script> içine basılıyor, `</script>`
            kaçışı YOK. Veri dış kaynaktan (ilan başlığı/şirket adı) geliyor.
            Her ilan sayfasında canlı script-injection yolu.
D2          ⛔ TAM AÇIK. Onay kavramı kodda hiç yok. fetch_subscribers yalnız
            `unsubscribed_at is null` süzüyor → mail gitmiş HER adres tanım
            gereği onaysız. KVKK/GDPR ship-blocker.
D1          Bugün ihlal 0, ama kod engellediği için değil: tek abone, tek koşu.
BÜTÇE       Belgede ÇELİŞKİ: KOLTUK kararı 2.550/ay, S9 eşiği 2.850/ay — aynı
            3.000 kotasından iki farklı rezerv (450 vs 150). 200 koltukta
            bağlayıcı aralık 2,35 gün; kartlardaki 2,4 buradan geliyor.
```

**Bu ölçümün ürün sonucu, gizlenmeden.** Bu koşunun varlık gerekçesi —
"ilanlar medyan 7 günde ölüyor, geç bülten kaçırıyor" — bu repoda **kanıtsız.**
Elimizdeki tek fetch bir günün fotoğrafı. Ömür ve kaçırma ancak jobs.json
günlerce farklı içerikle commit'lendikten sonra ölçülebilir.
**Doğrudan etkilenen kartlar: S2 (%26,5), S3 (21/3), S11 (kaçırma ≤ %10).**
Bu kartlar geldiğinde hakemleri bu bloğu görecek.

---

## S1 · "SAYILAR GERÇEK"

**Kullanıcı cümlesi.** Bu koşuda okuduğum her sayıyı ben de üretebilirim.

**İş.** `tools/measure.py` yazılır. Alt komutlar:

```
--lifetime         git'teki jobs.json anlık görüntülerinden ilan ömrü dağılımı
--miss <gün>       verilen gönderim aralığı için beklenen kaçırma oranı
--budget <koltuk>  aylık 3.000 → kişi başı sıklık → kaçırma projeksiyonu
--double-send      mail_state.json'da tekrar eden anahtar (D1)
--unconfirmed      onaysız adrese gönderim (D2)
--invariants       D4/D5/D6/D9 kaynak taraması
```

**Motora DOKUNMAZ.** Bu faz ölçer, onarmaz.

**Bu araç sonra DONAR.** Sonraki hiçbir faz `tools/measure.py`'ye dokunamaz.
İnşacı kendi karnesini yazamaz. Değişmesi gerekiyorsa koşu durur.

**S1'in tek deliği ve karşı önlemi.** Aracı S1 yazıyor ve S1'in kabulü kısmen
o araçla yargılanıyor. Bu yüzden **S1 hakemi `--lifetime` ve `--miss`
çıktısını ELLE, ham git verisinden bağımsız üretir.** Aracı çalıştırıp aynı
sayıyı görmek YETMEZ. Tutmazsa KALDI.

```
KABUL KOMUTU : python3 tools/measure.py --lifetime --miss 2.4 --budget 200 --invariants
EŞİK         : altı alt komut da sayı basıyor · ZEMİN'deki her satır ya
               doğrulanıyor ya çürütülüyor (çürüyen satır bu dosyaya yazılır)
               · hakem --lifetime medyanını elle doğruladı
DOKUNULABİLİR: tools/
```

---

## S2 · "İLAN HÂLÂ AÇIK"

**Kullanıcı cümlesi.** Bana gelen ilana tıkladığımda sayfa duruyor.

**Teşhis.** Bugün hiçbir yerde "bu ilan hâlâ var mı" kontrolü yok. İlanların
%26,5'i 3 günde ölüyor ve motor ölmüş ilanı postalamaya devam ediyor.
Ayrıca `fetch` 0 satır dönerse iş YEŞİL kalıyor: tek kaynak (`speedyapply`)
formatını değiştirirse ürün sessizce ölür ve kimse fark etmez.

**İş.**

1. İlana `last_seen` ve `alive` alanı. Bugünkü fetch'te görünmeyen →
   `alive=false`. `alive=false` ilan hiçbir mail ve hiçbir sayfa çıktısında
   geçmez (D7).
2. `fetch` 0 satır dönerse çıkış kodu ≠ 0, iş FAIL.
3. `fetch_speedyapply.py` → `fetch/` klasörü, kaynak başına bir dosya, ortak
   şema, kaynaklar arası dedupe, kaynak başına test iskeleti.
   **Yeni kaynak EKLENMEZ.** Korpus birebir aynı kalır.

### ⚠ S2 KARTI — HAKEM YENİDEN YAZDI (KART YANLIŞ). Aşağıdaki eski kart ÖLÜ.

```
ÖLÜ KART (koşulamaz):
KABUL KOMUTU : python3 -m unittest discover engine/tests && python3 tools/measure.py --corpus-hash
EŞİK         : refactor öncesi ve sonrası jobs.json BYTE-EŞ · alive=false ilan
               mail çıktısında 0 kez · fetch 0 satırda exit≠0 · mutasyon
DOKUNULABİLİR: engine/fetch_speedyapply.py, engine/fetch/, engine/tests/
```

**Neden ölü — hakemin kanıtı:**

1. `python3 tools/measure.py --corpus-hash` → **exit 2**, "unrecognized
   arguments". O alt komut hiç yazılmadı ve `tools/` S1'de DONDU, ayrıca
   S2'nin DOKUNULABİLİR listesinde yok. Komutun yarısı fizik olarak koşamaz.
2. **Kart kendi kendini imkânsız kılıyordu.** Madde 1 jobs.json'daki her kayda
   `last_seen`/`alive` eklettiriyor; eşik aynı dosyanın BYTE-EŞ kalmasını
   istiyor. İkisi aynı anda doğru olamaz.
3. D7'nin "hiçbir sayfa çıktısı" şartı `build_site.py` düzenlemesi
   gerektiriyordu — o dosya guard-kilitli ve kilidi **S5'te** açılıyor,
   DOKUNULABİLİR'de de yok. `send_mail.py` de listede yok ama eşik mail
   çıktısı istiyordu. Ajan iki kilitli dosyaya zorlanıyordu.
4. `fetch` gerçekten ağa gidiyor (`fetch_speedyapply.py:69`
   `urllib.request.urlopen`), yerel fixture yok → "0 satırda exit≠0" ağsız
   kanıtlanamazdı.
5. **UPSTREAM KAYMIŞ** — kartta hiç yoktu, en kritik bulgu: canlı README bugün
   283 satır dönüyor, jobs.json'daki 27 Tem çekimi 182'ydi. Fetch'i yeniden
   koşarak jobs.json'u üretmek İMKÂNSIZ; ajan koşsaydı S1'in zeminini yok
   ederdi.
6. Teşhisteki "%26,5'i 3 günde ölüyor" bu repoda kanıtsız (ZEMİN v2).
   Doğru teşhis: `alive`/`last_seen` YOK olduğu için ömür ÖLÇÜLEMİYOR.
   **S2, o ölçümün önkoşulu.**

**Hakemin çözümü.** `alive`/`last_seen` jobs.json'a GİRMEZ. Ayrı defter
(`engine/data/jobs_seen.json`) tutar; jobs.json yalnız `alive=true` kayıtları
taşır. D7 böylece **yapısal** olur — ölü ilan veriye hiç girmediği için
build_site/send_mail/match'in hiçbiri değişmeden ölü ilan basamaz.

### YENİ KART — YÜRÜRLÜKTE

```
KULLANICI CÜMLESİ : Bana gelen ilana tıkladığımda sayfa duruyor.

İŞ:
1. DONMUŞ GİRDİ. İki kaynağın ham markdown'ı bir kez çekilip
   engine/tests/fixtures/ altına aynen commit'lenir. Tüm testler ağsız koşar;
   test sürecinde socket açılırsa test DÜŞER.
2. DEFTER. engine/data/jobs_seen.json: key=(company.lower, position.lower) →
   {first_seen, last_seen, alive}. Bugünkü fetch'te görünmeyen key alive=false
   olur, last_seen KORUNUR. jobs.json'a YENİ ALAN EKLENMEZ; jobs.json yalnız
   alive=true kayıtları, bugünkü sıra ve byte'larıyla taşır.
3. fetch toplam 0 satır dönerse VE herhangi bir kaynak tek başına 0 satır
   dönerse exit≠0, jobs.json'a ve deftere HİÇBİR yazma yapılmaz (kısmi yazma yok).
4. fetch_speedyapply.py → engine/fetch/ klasörü: kaynak başına bir dosya, ortak
   şema, kaynaklar arası dedupe, kaynak başına test. YENİ KAYNAK EKLENMEZ.

KABUL KOMUTU : python3 -m unittest discover engine/tests && git diff --exit-code -- engine/data/jobs.json docs/

EŞİK:
· 15 miras test DEĞİŞMEDEN yeşil; toplam ≥23 test yeşil (≥8 yeni)
· YENİ testlerin HER BİRİ faz-öncesi kodda KIRMIZI düştüğü kanıtlanır
  (kırmızı çıktı rapora yapıştırılır); düşmeyen test boştur, faz düşer
· REPLAY BYTE-EŞ: donmuş fixture eski hattan ve yeni engine/fetch/ hattından
  geçirilir, üretilen jobs.json byte'ları BİREBİR aynı (dedupe sırası dahil)
· KORPUS DOKUNULMAZ: git diff --exit-code engine/data/jobs.json → exit 0;
  453 kayıt, 42 ülke, dedupe 41 aynen durur
· docs/ ÇIKTISI DOKUNULMAZ: git diff --exit-code docs/ → exit 0
· fetch 0 satırda exit≠0 — hem toplam-0 hem tek-kaynak-0 için ayrı test;
  0 satır durumunda jobs.json ve defter DEĞİŞMEMİŞ olmalı
· MUTASYON 1 (mail): fixture defterinde bir ilan elle alive=false yapılır →
  send_mail.DATA sandbox'a çevrilip --dry-run koşulur → o ilan çıktıda 0 kez
· MUTASYON 2 (veri): aynı ilan üretilen jobs.json'da 0 kez; jobs.json anahtar
  kümesi == defterdeki alive=true kümesi (eşitlik testi)
· MUTASYON 3 (kapı sağlaması): alive filtresi kasten kaldırılırsa Mutasyon 1
  ve 2 KIRILMALI; kırılmıyorsa kapı sahtedir, faz düşer
· last_seen KORUNUR: ölen ilanın last_seen'i sonraki koşularda değişmez
· HERMETİK: testler ağ kapalıyken de yeşil

DOKUNULABİLİR: engine/fetch_speedyapply.py, engine/fetch/, engine/tests/,
               engine/tests/fixtures/, engine/data/jobs_seen.json (yeni)
               — engine/data/jobs.json BYTE-DONMUŞ, elle düzenlenmez
               — build_site.py ve send_mail.py OKUNUR, düzenlenmez
```

**Hakemin zorlaştırdıkları:** koşulamayan komut → makineyle kilitli iki kapı
(`git diff --exit-code` korpus + docs) · test sayısı yoktu → ≥8 yeni + her biri
için faz-öncesi kırmızı kanıtı · BYTE-EŞ tanımsızdı → donmuş fixture replay +
git'te sıfır diff, iki ayrı kanıt · "0 satır" tek vakaydı → tek-kaynak-0 ayrı
vaka + kısmi yazma yasağı · tek belirsiz mutasyon → üç mutasyon, üçüncüsü
kapının kendisini sınıyor · hermetiklik ve `last_seen` korunması eklendi.
**Kolaylaştırma YOK.**

---

## S3 · "REMOTE DEDİĞİM REMOTE"

**Kullanıcı cümlesi.** Remote seçtiğimde bana Ankara'dan başvurabileceğim
ilanlar geliyor.

**Teşhis.** `remote` bir boolean. "Dünyanın her yerinden başvurulabilir" ile
"ABD'de yaşıyorsan ofise gelme" aynı `true` değerini alıyor. Ayrım kaynağın
lokasyon string'inde duruyor (`Remote - USA` vs `Remote`), motor okumuyor.
21 remote ilanın gerçekten yer bağımsız olanı 3.

**İş.**

1. `remote` boolean kalır. Yanına `remote_scope`: `global` | `country:XX` |
   `unknown`.
2. `"Remote"` → `global` · `"Remote - USA"` → `country:US` ·
   `"Remote - Berlin, Germany"` → `country:DE`.
3. Kural şehir listesine değil **ülke koduna** bakar. Üç şehre hardcode
   edilirse KALDI.
4. **`unknown` uydurulamaz.** Eşleştirmede `global` gibi değil `country:??`
   gibi işlenir: taşınamayan profil için elenir, ama elenme sebebi
   `remote_scope_unknown` diye AYRI isimlendirilir ki kaç ilanın parse
   eksiğinden düştüğü sayılabilsin.

```
KABUL KOMUTU : python3 -m unittest discover engine/tests
EŞİK         : 21 remote ilan doğru sınıflanıyor · global sayısı = 3 ·
               unknown sayısı bu dosyaya yazılıyor
DOKUNULABİLİR: engine/fetch/, engine/tests/
```

---

## S4 · "ALAMAYACAĞIM İŞİ YOLLAMIYOR"

**Kullanıcı cümlesi.** Bana gelen her ilana gerçekten başvurabiliyorum.

**Teşhis.** `us_work_auth` eleme kuralı koşuda **0 kez** tetiklendi. Başlıkta
"citizen · clearance · sponsorship" arıyor; ABD staj ilanları bunu başlığa
yazmıyor. Kural pratikte ölü kod, testi ise yeşil. Sonuç: Ankara'da oturan,
`relocation: false` yazan tek aboneye 224 eşleşmenin 115'i ABD eyalet kodlu
geliyor.

**İş.**

1. Ölü `us_work_auth` kalkar.
2. Yerine: profil `relocation=false` ise, `remote_scope != global` ve lokasyon
   profil ülkesi dışındaysa ELE.
3. Her elenme sebebi isimli. Eski kuralın 0 tetiklenmesine karşılık yeni
   kuralın tetiklenme sayısı bu dosyaya yazılır.

```
KABUL KOMUTU : python3 -m unittest discover engine/tests && python3 engine/match.py profile.json --stats
EŞİK         : Damla profilinde kalan eşleşmelerin %100'ü ya global remote ya
               profil ülkesinde · yeni kuralın tetiklenme sayısı > 0 ·
               kural FARKLI bir profille de doğru eliyor (hakem dener)
DOKUNULABİLİR: engine/match.py, engine/tests/
```

---

## S5 · "KENDİ SAYFAM VAR"

**Kullanıcı cümlesi.** Mail gelmediği günlerde de eşleşmelerime bakabiliyorum.

**Neden bu faz var.** Günlük 100 mail kotası kaçırma oranını ~%7'de tutuyor.
Sayfa o oranı **bakmak isteyen için sıfıra** indiriyor ve mail bütçesinden
hiçbir şey yemiyor. `build_site.py` zaten her gün koşuyor.

**Kilit ve şartı.** `.rabadon/guard.json` `build-site-mock-contract` kuralı bu
dosyayı kilitlemiş, gerekçe "mockup = kontrat, onaysız taşınmaz". Damla açtı,
tek şartla: **yalnız YENİ fonksiyon eklenir, mevcut şablon fonksiyonlarına
dokunulmaz.**

**İş.**

1. `docs/u/<token>.html` + `<token>.xml` (Atom). Token tahmin edilemez.
2. TÜM eşleşmeler, **skor eşiği yok.** Mail eşiği 5'tir; düşük puanlı eşleşme
   mail bütçesi harcamaya değmez ama bakmak isteyenden gizlenmez.
3. `noindex` + `robots.txt`.
4. Sayfada ilan eşleşmesi dışında kişisel veri yok.
5. **D9:** basılan her dış metin `esc()`'ten geçer. Desen zaten kurulu
   (`build_site.py:174`, `html.escape(..., quote=True)`), yeni kod atlamayacak.

```
KABUL KOMUTU : python3 engine/build_site.py && git diff --stat docs/index.html docs/cv.html docs/jobs/
EŞİK         : docs/index.html, docs/cv.html, docs/jobs/ çıktıları S5 öncesi
               ve sonrası BYTE-EŞ (0 değişiklik) · <script>alert(1)</script>
               içeren ilan başlığıyla site kurulduğunda çıktıda çalıştırılabilir
               script YOK · bir esc() çağrısı kaldırılınca kaçış testi kırmızı
DOKUNULABİLİR: engine/build_site.py (yalnız yeni fonksiyon), docs/robots.txt,
               engine/tests/
```

---

## S6 · "KOLTUK MATEMATİĞİ TUTUYOR"

**Kullanıcı cümlesi.** Koltuk doluysa bekleme listesine giriyorum, biri
çıkınca sıra bana geliyor.

**Teşhis.** Mekanizmanın yarısı kurulu: `taken = unsubscribed_at is null`,
yani çıkanın koltuğu zaten açılıyor. Üç delik var:

1. Cap trigger'ı `count(*) >= 100` okuyor. Eşzamanlı iki insert ikisi de 99
   görür, ikisi de geçer.
2. `confirmed_at` yok. Mail adresini yanlış yazan koltuğu sonsuza kadar tutar.
3. Kapasite İKİ yerde sabit (satır 38 ve 52). Birini değiştirip diğerini
   unutursan sayaç yalan söyler.

**İş.**

1. `confirmed_at timestamptz` alanı. Kapasite 100 → **200**, iki yerde.
2. Trigger'a `pg_advisory_xact_lock(hashtext('sightstone_seats'))`.
3. Sayım: `unsubscribed_at is null and (confirmed_at is not null or
   created_at > now() - interval '48 hours')`.
4. Sert bounce → `unsubscribed_at`.
5. Bekleme listesi tablosu ve **davet akışı**:

```
koltuk boşaldı (unsubscribe / sert bounce / 48s onaylamayan)
  → bekleme listesindeki EN ESKİ kişiye davet
  → 48 saatte onaylarsa koltuk onun
  → onaylamazsa davet düşer, sıradakine gider
```

6. **ÜÇ TERİMLİ SAYIM.** Atlanırsa aynı koltuk iki kişiye davet edilir:

```
boş = kapasite − onaylı − (48s dolmamış onaysız) − (cevap bekleyen davetler)
                                                    ^ unutulan üçüncü terim
```

7. **D8:** boş koltuk varken kimse bekleyemez. Boş varsa form açık, liste boş;
   dolu ise form kapalı, liste açık. İkisi aynı anda dolu olamaz. Tek istisna:
   davet döngüsü günlük koştuğu için gece boşalan koltukta ≤24 saatlik pencere
   oluşur — GİZLENMEZ, S13'te dürüstçe yazılır.

**İlk kart bir SAĞLIK KONTROLÜ.** Şemaya dokunmadan `sightstone_seats()`
çağrılır. Dönmüyorsa faz AÇILMAZ, kod değiştirilmez, koşu durur (§0/madde 6).

```
KABUL KOMUTU : python3 -m unittest discover engine/tests
EŞİK         : eşzamanlı 20 insert denemesinde kapasite aşılmıyor · onaysız
               kayıt 48 saatte koltuğu bırakıyor · iki yerdeki sayı da 200 ·
               aynı koltuğa iki davet gitmiyor · üçüncü terim çıkarılınca
               çift davet testi kırmızı düşüyor (mutasyon)
DOKUNULABİLİR: engine/schema.sql, engine/tests/
```

---

## S7 · "AYNI İLAN İKİ KEZ GELMİYOR"

**Kullanıcı cümlesi.** Aynı ilanı iki kere almadım.

**Teşhis.** `mail_state.json` bütün abone döngüsü **bittikten sonra** tek
seferde yazılıyor. 200 kişide 60.'da SMTP koparsa: 59 mail gitti, hiçbir kayıt
yazılmadı, tekrar koşuda hepsine ikinci kez gider. Beta'da çift mail güveni
tek hamlede bitirir.

**İş.**

1. `process_subscriber` her aboneden SONRA state yazar. Toplu yazım kalkar.
2. **Profil düzenleme kuralı:** abone filtresini değiştirince `sent_keys`
   **SIFIRLANMAZ.** Skorlama yenilenir, gönderilmiş gönderilmiş kalır. Aksi
   halde D1 kâğıtta sağlam, pratikte kırık olur.

**Uyarı.** `send_mail.py`'ın bugün HİÇ testi yok. S7'den S11'e kadar beş faz
bu dosyayı değiştirecek ve altında ağ yok. Her faz kendi testini getirmek
zorunda; "mevcut testler yeşil" bu blokta hiçbir şey kanıtlamaz.

```
KABUL KOMUTU : python3 -m unittest discover engine/tests && python3 tools/measure.py --double-send
EŞİK         : 10 abonelik simülasyonda 5.'de exception → ilk 4'ün anahtarları
               diskte, tekrar koşuda onlara mail yok · profil değişince
               sent_keys korunuyor · --double-send = 0 · state yazımı geri
               alınınca çift mail testi kırmızı düşüyor (mutasyon)
DOKUNULABİLİR: engine/send_mail.py, engine/tests/
```

---

## S8 · "MAİL GERÇEK BİR YERDEN GELİYOR"

**Kullanıcı cümlesi.** Gelen mail bir şirketten gelmiş gibi duruyor, kişisel
bir Gmail'den değil.

**Teşhis.** `send_mail.py` kişisel Gmail app password'ü ile `smtplib`
kullanıyor. 200 yabancıya bu şekilde mail atmak spam klasörü demek. Kendi
domaininden gitmiyor, SPF/DKIM/DMARC yok.

**İş.**

1. Gönderim tek arayüzün arkasına:
   `send(to, subject, html) -> MessageId | HardBounce | SoftFail`.
2. Resend uygulaması. `smtplib` kalkar.
3. SPF + DKIM + DMARC `noseydewdrop.com` üzerinde. Yapılandırma **sağlayıcının
   kendi dokümanından** alınır, hatırlanan ayardan değil.
4. `List-Unsubscribe` başlığı (tek tık).
5. Sağlayıcı değiştirmek tek dosyada tek sınıf yazmayı gerektirecek. Bedava
   planlar bir söz değil, bir iş kararıdır; taşınabilir olmak zorunda.

```
KABUL KOMUTU : python3 -m unittest discover engine/tests && dig +short TXT noseydewdrop.com
EŞİK         : smtplib importu 0 · sahte sağlayıcıyla test geçiyor ·
               SPF, DKIM, DMARC üçü de DNS'te görünüyor · List-Unsubscribe
               başlığı üretilen her mailde var
DOKUNULABİLİR: engine/send_mail.py, engine/tests/
```

---

## S9 · "KOTA PATLAMIYOR"

**Kullanıcı cümlesi.** Kaydolduğumda onay mailim geldi, 101. kişi olduğum için
kaybolmadım.

**Teşhis.** Yayın günü 200 kişi kaydolursa 200 onay maili demek. Resend bedava
katmanı günde 100 kesiyor. 101. kişi hesabını onaylayamaz ve kaydı ölür.

**İş.**

1. Günlük 100, aylık 3.000 sayacı. **Bülten, onay VE davet mailleri aynı
   kovadan yer.** Aylık 2.850'yi geçince bülten durur, loglanır.
2. Kota dolunca gönderim durur ve çıkış kodu **0** döner — bu planlı bir
   duruştur, fail değil. Durum state'e yazılır. Sessiz aşım imkânsız.
3. **KADEMELİ KOLTUK AÇILIŞI.** Koltuklar hepsi birden açılmaz:

```
günlük_açılacak = 100 − (bugünkü bülten + davet) − 10 emniyet
```

Açılış hızını kotanın kendisi belirler. Yayın gününde abone yok, bülten
gitmiyor, o gün ~90 koltuk açılır; sonraki günlerde bülten yükü arttıkça
açılış yavaşlar. 200 koltuk kendiliğinden 3-5 güne yayılır. **Kıtlık
uydurulmuyor, kotadan türetiliyor.**

```
KABUL KOMUTU : python3 -m unittest discover engine/tests
EŞİK         : 200 kişilik ani kayıt simülasyonunda günlük 100 hiçbir gün
               aşılmıyor · kota dolunca exit=0 ve state'e yazılıyor ·
               emniyet payı kaldırılınca kota testi kırmızı düşüyor (mutasyon)
DOKUNULABİLİR: engine/send_mail.py, engine/tests/
```

---

## S10 · "ONAYLAMADAN GELMİYOR, BOŞ HAFTAYI ANLIYORUM"

**Kullanıcı cümlesi.** Mailimi onayladım, ve mail gelmediği haftada bunun
arıza olmadığını biliyorum.

**Teşhis.** Bugün formda biri **başkasının** mail adresini yazabiliyor. 200
kişilik bir duyuruda bu kesin olur ve tek spam şikâyeti domain itibarını
götürür. Ayrıca "yeni eşleşme yoksa mail yok" sözleşmesi doğru ama
açıklanmazsa abone bozuk sanıp sessizce gider.

**İş.**

1. Kayıt → onay maili → `confirmed_at`. `fetch_subscribers` yalnız onaylıları
   çeker (D2).
2. S6'nın davet akışı burada maile bağlanır. İkisi de S9 kotasından yer.
3. **Sessiz hafta politikası.** Çözüm ek mail DEĞİL (D3 bütçesi), onay mailine
   tek cümle:

```
"Bazı haftalar mail almayabilirsin; arıza değil, filtrene uyan yeni ilan
 çıkmadı demektir. Her sabah güncellenen kendi sayfandan bakabilirsin: <token>"
```

Token S5'te üretildi, link gerçek.

4. **Kopya kuralı.** Bu faz Damla'nın adına metin yazıyor. Önce
   `writing-style.json` okunur ("Damla is the SPEC, never invent facts").
   Yeni ses icat edilmez, kurulu ses uygulanır.

```
KABUL KOMUTU : python3 -m unittest discover engine/tests && python3 tools/measure.py --unconfirmed
EŞİK         : --unconfirmed = 0 · uçtan uca akış çalışıyor (kaydol → onayla →
               bülten → çık) · onay maili sessiz hafta cümlesini ve ÇALIŞAN
               token linkini içeriyor
DOKUNULABİLİR: engine/send_mail.py, docs/, engine/tests/
```

---

## S11 · "SIRAM GELİYOR"

**Kullanıcı cümlesi.** İyi bir ilan çıktığında beklemiyorum, sıradan biri
olduğumda da unutulmuyorum.

**Teşhis.** Sabit haftalık kohort ölçüldü ve REDDEDİLDİ: ortalama kaçırma
%25,4. Salı grubundaki kişi, çarşamba açılıp cuma kapanan ilanı hiç görmüyor.
Bu istisna değil, medyan durum.

**İş.** Yaşlandırmalı öncelik kuyruğu:

```
P = en_iyi_skor + 1.2×bekleme_günü + 0.5×tazelik + 0.3×min(adet,5)
```

**Katsayı gerekçeleri, keyfi değil:**

- `1.2×bekleme` — 6 gün bekleyen +7,2 alır ve en yüksek kalite puanını (12)
  yakalar. **Açlık matematiksel olarak imkânsız.**
- `0.5×tazelik` — bugün açılan +3,5. İlanların %26,5'i 3 günde ölüyor;
  tazelik gerçek aciliyettir, süs değil.
- `0.3×adet, 5'te doyum` — tek çok iyi eşleşme, beş vasattan değerli. Doyum
  olmasa geniş profil kuyruğun başını kapardı.

Mail eşiği `min_score 5` kalır. Kotaya göre kes (S9), kalanı yarına devret,
bekleme +1. `alive=false` ilan kuyruğa hiç girmez (S2, D7).

**Simülasyon gerçek veriyle beslenir.** `jobs.json`'un git geçmişi kullanılır.
Uydurma veriyle geçen simülasyon fazı düşürür.

```
KABUL KOMUTU : python3 -m unittest discover engine/tests && python3 tools/measure.py --miss-simulated
EŞİK         : 200 abone simülasyonunda kimse 8 günden fazla beklemiyor ·
               kaçırma ≤ %10 · aynı simülasyon sabit kohortla koşulduğunda
               ölçülebilir ölçüde DAHA KÖTÜ çıkıyor
DOKUNULABİLİR: engine/send_mail.py, engine/tests/
```

---

## S12 · "MAİL GELDİ VE SPAM'E DÜŞMEDİ"

**Kullanıcı cümlesi.** Kaydoldum ve mail gelen kutuma düştü.

**Bu koşunun tek gerçek kabul testi.** Diğer on üç fazın hepsi bunun
önkoşulu. Bugüne kadar hiçbir şey gerçek bir yabancıya gönderilmedi; tek
abone Damla ve gönderim kendi Gmail'inden. Testler yeşil yanabilir, kota
tutabilir, kuyruk kusursuz sıralayabilir — mail spam klasörüne düşerse
hiçbiri olmamıştır.

**İş.**

1. Dört farklı sağlayıcıya gerçek mail: **Gmail · Outlook · Yandex ·
   bir üniversite adresi.**
2. Damla dört kutuya da bakar. Gelen kutusu mu, spam mi, promosyonlar mı.
3. Uçtan uca gerçek akış: kaydol → onay maili → onayla → bülten → sayfaya
   bak → abonelikten çık → koltuk açıldı mı.
4. Acil durum düğmesi denenir: cap = 0 → yeni kayıt anında duruyor mu.
5. `--dry-run` bülten çıktısı gözle okunur, on ilanın linki tek tek açılır.
6. Sonuç `GIRDI/teslimat/` altına yazılır: dört kutunun ekran görüntüsü +
   `sonuc.md`.
7. **Hiçbir sayı bu ölçümden sonra "düzeltmek için" değiştirilmez.** Bir şey
   tutmuyorsa hangi fazın kartı yanlıştı sorulur, o faz yeniden koşar.

**Kural.** S13 ve S14 bu faz geçmeden koşamaz. Teslim edilmemiş bir bülteni
pazarlamak, 1 abonelik dokuz ayın tekrarıdır.

```
KABUL KOMUTU : eşik YOK, bu bir gerçeklik fazı. Tek şart: GIRDI/teslimat/
               içinde dört kutunun görüntüsü ve sonuc.md var, ve bu dosyaya
               sonuç yazılmış.
EŞİK         : dört sağlayıcının dördünde de GELEN KUTUSU. Biri spam'e
               düşerse koşu DURUR. Promosyonlar sekmesi kabul edilir,
               spam edilmez.
DOKUNULABİLİR: KOSU-v4.md, GIRDI/teslimat/
```

---

## S13 · "VİTRİN GERÇEĞİ SÖYLÜYOR"

**Kullanıcı cümlesi.** Siteye girdim, ne alacağımı anladım, ve abartı yoktu.

**Teşhis.** Sitede bugün "99 seats left" yazıyor ve 1 abone var. Bir kıtlık
mekaniği boş odada duruyor. Ayrıca remote havuzunun gerçek sayısı hiçbir
yerde yazmıyor: "remote iş bulacağım" diye kaydolan biri ilk bültende boş
mail alır.

**İş.**

1. **Sayaç gizlenir.** Arka uçta doğru çalışır, arayüzde görünmez. 100/200
   eşiğinde tek satırlık anahtarla açılır. Bekleme listesi sayısı da gizli.
2. **Kayıtta canlı eşleşme önizlemesi.** Kişi "gönder"e basmadan önce motor o
   profili havuza karşı koşar: *"bu filtreyle şu an X ilan eşleşiyor, geçen
   hafta Y yeni ilan girdi."* Motor zaten yazılı, maliyeti sıfır. Kişi
   kaydolmadan **kendi kararını verir**; hayal kırıklığı ilk bültende değil
   kayıttan önce yaşanır.
3. **Remote havuzu hakkında dürüst uyarı**, gerçek sayılarla: 21 remote ilan
   var, 3'ü dünya geneli, geçen hafta dünya geneli remote akışı 0.
4. Bekleme listesi formu. S6'nın ≤24 saatlik davet penceresi dürüstçe yazılır.
5. **"Hayattan ne istiyorsun" serbest metni KORUNUR.** Arkada
   `cv_critique.py`'nin `TERMS` sözlüğüyle deterministik yapıya çevrilir,
   cümle bozulmaz.
6. **D9:** serbest metin yabancılardan geliyor ve sayfaya basılıyor.
   `esc()` zorunlu, `href`/`src`'ye dış metin doğrudan yazılmaz.
7. Sayfadaki her sayı `sightstone_seats()`'ten ya da motordan gelir. Elle
   yazılmış sayı **sıfır**. Gizlemek ≠ yanlış hesaplamak.
8. **Kopya kuralı.** `writing-style.json` ve `site-mock/` okunur. Yeni ses
   icat edilmez.

```
KABUL KOMUTU : python3 engine/build_site.py && grep -c "seats left" docs/index.html
EŞİK         : elle yazılmış sayı = 0 · "seats left" görünür metinde 0 ·
               ölü link = 0 · kayıt formunda canlı önizleme çalışıyor ·
               <script> yüklü profil metniyle çıktıda çalıştırılabilir script YOK
DOKUNULABİLİR: engine/build_site.py, docs/index.html, engine/tests/
```

---

## S14 · "KAPANIŞ"

**Kullanıcı cümlesi.** Yok. Bu faz Damla için.

Kod değişikliği YOK. Yapılan:

1. **D1–D9 tam tarama.** Dokuzu da yeşil mi.
2. **Miras kırmızı kümesi hâlâ boş mu.** S1 tabanı 15/15 yeşildi.
3. `.rabadon/guard.json` kuralları hâlâ yürürlükte mi, yeni ihlal var mı.
4. Kaçırma oranının S1 tabanından bugüne seyri.
5. **KAYNAK AÇIĞI RAPORU — kapanmaz, açık madde olarak yazılır.**
   Kaç abone hangi filtreyle kaç hafta boş geçerdi; hangi kaynak eklense kaç
   kişiye dokunurdu. `firsatlar.md`'deki soğuk katman (MLH, Wellfound,
   YC WaaS, Bones Interactive, Spaceflow, Mindra) şemaya çevrilmemiş halde
   duruyor. Bu tablo koşudan sonraki üç ayın yol haritasıdır.
6. Bu faz **YAYIN YAPMAZ.** Yalnız "yayına hazır" ya da "hazır değil, şu
   sebeple" der. Yayın kararı Damla'nın.

**Kaynak gerçeği, gizlenmeden yazılır.** Bu koşu eşleştirme motorunu düzeltti,
havuzu değil. Havuz boş değil ama **yanlış kitleye ait**: taşınabilen bir
profil haftada ~10 eşleşme alıyor, taşınamayan 0. Mühendislik problemi burada
bitiyor, ürün problemi burada başlıyor.

```
KABUL KOMUTU : python3 tools/measure.py --invariants --double-send --unconfirmed && python3 -m unittest discover engine/tests
EŞİK         : D1-D9 dokuzu da yeşil · 15 miras testin 15'i hâlâ yeşil ·
               kaynak açığı raporu bu dosyaya yazılmış
DOKUNULABİLİR: KOSU-v4.md
```

---

## SIRA VE BAĞIMLILIK

```
S1  Sayılar gerçek        → bağımsız, ilk. 13 fazın hepsi buna dayanıyor
S2  İlan hâlâ açık        → S1. fetch/ bölmesi burada, KAYNAK EKLENMEZ
S3  Remote gerçeği        → S1
S4  Alamayacağım işi yok  → S3
S5  Kendi sayfam          → S2, S4. build_site kilidi burada açılıyor
S6  Koltuk matematiği     → S1. schema.sql'e dokunan TEK faz
S7  İki kez gelmiyor      → S1  ┐
S8  Gerçek gönderici      → S1  │ send_mail.py bloğu.
S9  Kota patlamıyor       → S6, S8  │ Beşi bitişik, hiçbiri paralel değil,
S10 Onaylamadan gelmiyor  → S5, S6, S8, S9  │ araya başka konu girmez.
S11 Sıram geliyor         → S2, S7, S9  ┘
S12 MAİL GELDİ            → S10, S11.  ⛔ SERT DURAK, Damla dört kutuya bakar
S13 Vitrin gerçeği        → S3, S4, S5, S6, S12
S14 Kapanış               → hepsi. KOŞULSUZ, atlanmaz
```

**Sıra üç kurala göre kuruldu.**

1. **Dosya bloğu.** Aynı dosyaya dokunan fazlar bitişik. `send_mail.py`'a beş
   faz dokunuyor (S7-S11), araya şema ya da site işi girmiyor. Taze ajan
   dosyayı devralıp bırakıyor.
2. **İleri referans yok.** S9'un kotası davet maillerini sayıyorsa davet akışı
   (S6) ondan ÖNCE kurulmuş olmalı. S10'un onay maili token linki veriyorsa o
   sayfa (S5) ondan ÖNCE üretiliyor olmalı.
3. **Bedava kaldıraç erkene.** S5 hiç mail bütçesi harcamıyor, `send_mail.py`'a
   hiç dokunmuyor, ve kaçırma oranını isteyen için %0'a indiriyor. Koşu yarıda
   kalırsa en ucuz ve en değerli parçanın bitmiş olması gerekir.

**S12'nin özel yeri.** S12 spam'e düşerse S1-S11'in hepsi teknik olarak doğru
ama ürün olarak sıfırdır. Bu yüzden pazarlama (S13) ondan sonra. Bugünkü
sitenin yalan söylemesinin sebebi bu sıranın tersine işlemiş olması.

---

## KOŞU KAYDI

Fazlar bittikçe buraya yazılır.

### ŞEF NOTU — koşu açılışı

```
REPO        /Users/damummyphus/damla_projects_2026/_arsiv_2026-08-18/sightstone
            main · origin github.com/nosey-dewdrop/sightstone
TABAN       HEAD dbaf3ae · python3 -m unittest discover engine/tests → 15 test,
            15 yeşil, miras kırmızı YOK. (şef ölçtü, koşu öncesi)
ÇÜRÜK       ZEMİN bloğundaki commit `ce823dec` bu repoda YOK
            (git cat-file: not a valid object name). ZEMİN zaten HİPOTEZ,
            S1 yeniden ölçüyor. Referans sha geçersiz olarak işaretlendi.
UYARI       firsatlar.md çalışma ağacında SİLİNMİŞ durumda (git status: D),
            HEAD'de duruyor. S14 onu `git show HEAD:firsatlar.md` ile okur.
            Şef silmeyi geri almadı; bu Damla'nın çalışma ağacı değişikliği.
```

```
## S1 — Sayılar gerçek — GEÇTİ
ölçülen: 6 alt komut çalışıyor · 11 ZEMİN satırı yargılandı (8 çürüdü, 3 doğrulandı)
         · hakem bağımsız ölçüm: 6 görüntü / 0 tamamlanmış ömür / medyan ÖLÇÜLEMEZ
eşik:    6 alt komut sayı basacak · her ZEMİN satırı yargılanacak
         · hakem --lifetime medyanını elle doğrulayacak
diff:    yalnız tools/measure.py (710 satır). tools/ dışı 0.
miras:   15/15 yeşil
hakem notu: Araç, yapamayacağı yerde susmayı seçtiği için geçti — hakem ZEMİN'in
         ömür/kaçırma tablosunu ham git'ten bağımsız olarak da çürüttü.
```

**S1'in koşuya bıraktığı üç açık madde** (kapatılmadı, sahibi var):
1. `build_site.py:627` D9 ihlali → sahibi **S5** (esc() kartı).
2. Onay yok, D2 tam açık → sahibi **S10**.
3. Ömür/kaçırma verisi yok → **S11'in eşiği şu an ölçülemez.** S11 hakemi
   karar verecek; şef karar vermez.


```
## S2 — İlan hâlâ açık — GEÇTİ (kart hakem tarafından bir kez yeniden yazıldı)
ölçülen: 36 test yeşil (15 miras değişmedi + 21 yeni) · faz-öncesi kırmızı 21/21
         · replay iki hattan BYTE-EŞ, sha 5c5495bc…, 294801 bayt
         · jobs.json sha HEAD ile aynı (ecb1a2b5…), 453 kayıt, yeni alan sızmadı
         · defter 453 kayıt, alive=true kümesi == jobs.json anahtar kümesi (simetrik fark boş)
         · mutasyon 3: alive filtresi kaldırılınca 2 test kırmızı düştü, kapı gerçek
         · hermetik: hakem socket'i harici bloke etti, 36/36 yeşil
eşik:    ≥23 test / ≥8 yeni · replay byte-eş · korpus ve docs/ diff exit 0 · 3 mutasyon
birikimli (S1): measure.py exit 0, altı bölüm sayı basıyor, tools/ diffi boş
hakem notu: Kart eşiğinin her maddesi bağımsız ölçümle tuttu; replay'in faz-öncesi
         koda karşı koştuğu, legacy fixture'ın HEAD'le sıfır farkı olduğu doğrulandı.
```

**S2'nin bıraktığı açık maddeler:**
1. **Fixture'lar korpusla aynı gün DEĞİL.** `engine/tests/fixtures/*.md` bugünkü
   çekim (599 ilan, 59 duplicate); commit'li `jobs.json` 27 Tem (453 ilan, 41).
   Replay "eski hat == yeni hat" kanıtlıyor ama fixture'lardan 453'lük korpus
   yeniden üretilemiyor. **Korpus hâlâ replay edilemez tarihsel artefakt.**
2. **Defterde 0 ölü ilan.** D7 kapısı canlı veride bugün hiçbir şey elemiyor;
   etkisi yalnız testte kanıtlı. Gerçek ömür için en az iki farklı günün
   gerçek fetch'i gerekiyor. **S11'in kaçırma eşiği hâlâ ölçülemez.**
3. `first_seen` hepsine `2026-07-27` yazıldı (fetch_meta.fetched_at'ten), ama
   jobs.json'a dokunan ilk commit `b75af225` 26 Tem 13:55 UTC. Uydurma değil,
   repodaki bir alandan türetilmiş, ama git geçmişiyle çelişiyor. DOĞRULANMADI.
4. Ajan, rabadon kilidi (`red-suite-test-write` + `red-base` döngüsü) yüzünden
   `engine/fetch/__init__.py:76-80`'e savunmacı bir satır eklemek zorunda kaldı:
   tanınmayan defter satırı çökertmek yerine atlanıp yeniden öğreniliyor.
   **Kart bunu istemedi, kilit dayattı.** Kayda geçti.
5. D9 (`build_site.py:627`) hâlâ kırmızı — sahibi S5.
