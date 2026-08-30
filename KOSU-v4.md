# SIGHTSTONE KOŞUSU v4 — SON KOŞU

## AÇIK MADDELER — kapatılmadı, sahibi var, S14 tek tek işaretleyecek

Bunlar bulundu ve **bilerek açık bırakıldı**. Hiçbiri "sonra bakarız" değil;
her birinin sahibi olan bir faz var ve S14'ün kapanış taraması dokuzunu da
tek tek işaretlemeden koşu bitmez.

| # | ne | nerede | sahibi |
|---|---|---|---|
| A1 | `json.dumps` çıktısı `</script>` kaçışı olmadan `<script>` içine basılıyor. **Canlı XSS yolu, D9 ihlali.** Veri dış kaynaktan (ilan başlığı/şirket adı) geliyor, her ilan sayfasında canlı. | `engine/build_site.py:627` | **S5** |
| A2 | **S1'in `--invariants` kapısı A1'i exit 0 ile geçirdi.** Yani kapı ihlali GÖRÜYOR ama BLOKLAMIYOR. Kapının kendisi de düzeltilecek: D9 kırmızıysa çıkış kodu ≠ 0. | `tools/measure.py` | **S5** (`tools/` donmuştu; bu tek istisna Damla tarafından açıldı) |
| A3 | `cv_text` sütunu var, yazan kod yok. D5 bugün yeşil ama **şema CV'yi sunucuda saklamaya HAZIR.** Boş sütun silinecek. | `engine/schema.sql:18` | **S6** |
| A4 | **Onay kavramı kodda hiç yok.** `fetch_subscribers` yalnız `unsubscribed_at is null` süzüyor → gitmiş her mail tanım gereği onaysız. D2 tam açık, **KVKK ship-blocker.** | `engine/send_mail.py` | **S10** |
| A5 | ⛔ **`test_engine.py:29` hâlâ canlı korpusa çivili ve mail'i öldürebilir.** `assertGreater(matched, 200)`; `cv_critique` canlı `jobs.json` üzerinde sayıyor. Ölçüldü: **sabah fetch'i 273 ilanın altına düşerse bu test kızarır, `daily.yml` fail eder, MAİL GİTMEZ.** Bugün 323/453, %40 pay var. İŞ 2 diğer tüm çivileri söktü ama bu dosya "miras test değiştirilemez" kuralıyla, `cv_critique.py` de kapsamla korunuyordu. **Kendi kartını hak ediyor.** | `engine/tests/test_engine.py:29`, `engine/cv_critique.py` | **kartsız — Damla'nın sıraya sokması gerek** |
| A6 | Ömür ve kaçırma oranı **bu repoda ÖLÇÜLEMİYOR** (0 doğum, 0 ölüm, %100 sansür). **S11'in "kaçırma ≤ %10" eşiği şu an ölçülemez.** S11 gelince koşu yine duracak. | `engine/data/jobs_seen.json` bugün tek günlük | **S11** |
| A7 | `tools/measure.py:112 country_of()` ile `common.py:listing_country()` **aynı işi yapan iki ayrı kural.** Biri ülke adı döndürüyor ve `anywhere`/`worldwide`'ı tahmin ediyor (S3'ün yasakladığı şey), diğeri ISO kodu döndürüyor ve tahmin etmiyor. `test_fetch.py` birincisine bağlı. | `tools/` vs `engine/fetch/` | **S14** raporuna |
| A8 | `+3 "location fits"` bonusu, hiç ilgi/beceri eşleşmesi olmayan ilanı sırf ülkende diye eşiğin üstüne çıkarıyor (US profilinde `no_signal` 258 → 0). **Puanlama eşiğinin ayrı zayıflığı.** TR'de etkisi sıfır (korpusta TR ilanı 0), başka profil eklenirse patlar. | `engine/match.py` | **kartsız** |
| A9 | `location_country_unknown` 34 ilan **sessizce eleniyor**; içlerinde gerçekten başvurulabilir iş olabilir. İçeriklerine bakılmadı. **DOĞRULANMADI.** | `engine/data/jobs.json` | **S14** raporuna |

**A5 en tehlikelisi.** Diğerleri bir gün geciktirilebilir; A5 bir sabah
sessizce mailin hiç gitmemesine yol açar ve kimse fark etmez — bu koşunun
düzeltmeye çalıştığı hatanın ta kendisi.

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

### ⚠ S3 KARTI — HAKEM YENİDEN YAZDI (KART YANLIŞ). Aşağıdaki eski kart ÖLÜ.

```
ÖLÜ KART:
KABUL KOMUTU : python3 -m unittest discover engine/tests
EŞİK         : 21 remote ilan doğru sınıflanıyor · global sayısı = 3 ·
               unknown sayısı bu dosyaya yazılıyor
DOKUNULABİLİR: engine/fetch/, engine/tests/
```

**Neden ölü — hakemin bağımsız ölçümü:**

| korpus | remote | düz "Remote" | çivili | parse edilemeyen |
|---|---|---|---|---|
| `engine/data/jobs.json` (453) | **28** | **9** | 19 | 0 |
| `engine/tests/fixtures/` (540 dedupe'lu) | **21** | **3** | 18 | 0 |

Eski kartın "21 / 3" sayıları **fixture'ın** sayılarıydı ama kart onları
jobs.json'a aitmiş gibi yazmıştı. Diğer kusurlar:

1. Eşik yalnız iki sayı istiyordu. 19 çivili ilanın hangi ülkeye düştüğü hiç
   sorulmuyor → ajan "Remote" içeren her şeyi US sayıp 28/9'u tutturabilir.
2. `unknown` iki korpusta da **0**. Yani korpus unknown yolunu HİÇ kanıtlamıyor;
   kart bunu bilmediği için sentetik test istemiyordu, sessiz default açıkta.
3. Kart kendi içinde çelişkiliydi: madde 4 `match.py` işi istiyor, DOKUNULABİLİR
   `match.py`'yi yasaklıyor. Çelişki listeden yana çözüldü, iş **S4'e yazılı
   borç** olarak geçti.
4. Asıl çatışma (yeni alan vs BYTE-DONMUŞ jobs.json) ajana bırakılmıştı.
   **Karara bağlandı: `remote_scope` TÜRETİLMİŞ, diske ASLA yazılmaz.**
   `common.py:FIELDS` ve `record()` bir harf değişmez. Ayrı defter reddedildi —
   `alive` gün-be-gün değişen bir DURUM, `remote_scope` saf fonksiyon.
5. Kabul komutu S2'nin byte kapılarını korumuyordu.
6. `+N` son eki (`Remote - USA +1`, `Remote - Boston, MA +3`,
   `Remote - Hong Kong +2`) tanımsızdı — 3 ilan tanımsız bölgede.
7. "Üç şehre hardcode edilirse KALDI" bir niyet beyanı, mekanik kapı değil.

**Ülke tablosu ölçüldü:** iki korpusun birleşiminde 48 kuyruk token'ı — 47'si
gerçek ülke/bölge, 1'i (`LATAM`) ülke DEĞİL, `unknown`a düşmek zorunda.
Ayrıca 27 farklı ABD eyalet kısaltması. stdlib'de ISO 3166 verisi YOK, harici
paket yasak → repo içi sabit tablo şart.

### YENİ KART — YÜRÜRLÜKTE

```
KULLANICI CÜMLESİ : Remote seçtiğimde bana Ankara'dan başvurabileceğim ilanlar geliyor.

İŞ:
1. `remote` boolean AYNEN KALIR. jobs.json'a YENİ ALAN GİRMEZ. common.py:FIELDS ve
   record() bir harf değişmez. `remote_scope` TÜRETİLMİŞ: common.py'de saf fonksiyon,
   ağsız, saatsiz, yan etkisiz.
2. Sözleşme: remote_scope(job) -> str | None
     job["remote"] False ise → None ("global" DEĞİL, "" DEĞİL)
     düz "Remote" → "global"
     "Remote - <yer>" → "country:XX" (ISO 3166-1 alpha-2, BÜYÜK harf)
     çözülemeyen → "unknown". Tahmin YASAK, en yakın eşleşme YASAK.
3. Kural ÜLKE KODUNA bakar, şehir listesi YASAK. Çözüm sırası:
     (a) son virgül-parçası ülke adı tablosunda mı → o kod
     (b) değilse 2 harfli ABD eyalet/bölge kodu mu → country:US
     (c) hiçbiri → unknown
   İKİ sabit dict common.py'de. ABD tablosu 50 eyalet + DC = 51 kodun TAMAMI
   (korpusta geçen 27 değil). Ülke tablosu ölçülen 47 adın TAMAMI. LATAM bir
   bölgedir, tabloya GİRMEZ, unknown'a düşer.
4. `+N` son eki scope'u DEĞİŞTİRMEZ: ilk yazılı yer belirler, +N yok sayılır.
5. scope_census(jobs) -> dict saf fonksiyonu; fetch/__init__.py:run() özet satırına
   scope dökümü basılır — unknown sayısı EKRANDA. Sessiz default yasak.
6. Eleme S3'ün işi DEĞİL. engine/match.py bu turda BİR HARF değişmez.

KABUL KOMUTU:
python3 -m unittest discover engine/tests 2>&1 | tail -3 && git diff HEAD --exit-code -- engine/data/jobs.json docs/ engine/match.py engine/tests/test_engine.py engine/build_site.py engine/send_mail.py tools/ && echo GATES-OK

EŞİK:
A. Test >= 47, hepsi yeşil (bugün 36 → en az 11 yeni). Miras test_engine.py 15/15,
   DEĞİŞMEMİŞ.
B. Kabul komutu GATES-OK basar: 7 yol bayt bayt değişmemiş (staged dâhil).
C. jobs.json census'u TAM SÖZLÜK EŞİTLİĞİ (== , >= değil):
   {"global":9, "country:US":14, "country:CA":2, "country:DE":2, "country:IN":1,
    "unknown":0}   toplam remote = 28
D. fixtures census'u TAM SÖZLÜK EŞİTLİĞİ:
   {"global":3, "country:US":14, "country:CA":1, "country:BE":1, "country:DE":1,
    "country:HK":1, "unknown":0}   toplam remote = 21
E. Unknown iki korpusta da 0 → SENTETİK unknown testi ZORUNLU. Şu 5 girdi unknown
   döndürmeli, hiçbiri global OLMAMALI:
   "Remote - LATAM" · "Remote - EMEA" · "Remote - Anywhere" · "Remote - " ·
   "Remote - Wakanda"   ("Anywhere" bilerek unknown: tahmin yasağı global tahminini
   de kapsar.)
F. remote=False ilan için remote_scope None döner — ayrı test.
G. ANTİ-HARDCODE KAPISI: korpusta HİÇ remote geçmeyen ülkeler de çözülmeli:
   Zurich, Switzerland→CH · Singapore→SG · London, United Kingdom→GB ·
   Amsterdam, The Netherlands→NL · Seoul, South Korea→KR ·
   Dubai, United Arab Emirates→AE
   Ayrıca test 47 ülke adını ve 51 ABD kodunu tek tek gezip her birinin çözüldüğünü
   doğrular. Şehir adı, tabloların hiçbirinde ANAHTAR olamaz.
H. +N testi: "Remote - USA +1"→US · "Remote - Boston, MA +3"→US ·
   "Remote - Hong Kong +2"→HK
I. MUTASYON — üçü de KIRMIZI düşmeli, düşen testin adı raporlanır:
   M1 remote_scope hep "global" dönsün → C,D,E,G,H düşer
   M2 ülke tablosu {USA,Canada,Germany,India} ile sınırlansın → D ve G düşer
      (HARDCODE'UN ÖLÇÜLEN HÂLİ)
   M3 unknown yerine sessizce "global" default'lansın → E düşer
   Tüm yeni testler remote_scope yazılmadan önce toplu KIRMIZI olmak zorunda.
J. Ağ yok, harici paket yok. Testler jobs.json ve fixtures/ dışında bir şey okumaz.

DOKUNULABİLİR: engine/fetch/ , engine/tests/ altında YENİ test dosyası ve
test_fetch.py. BUNUN DIŞINDA HİÇBİR ŞEY — özellikle match.py, test_engine.py,
jobs.json, fixtures/*.md, docs/, tools/, build_site.py, send_mail.py.
```

**Hakemin zorlaştırdıkları:** yanlış korpusun iki sayısı → iki korpusta ayrı ayrı
TAM SÖZLÜK EŞİTLİĞİ, ülke kırılımıyla · ülke kırılımı hiç ölçülmüyordu → 5+6 kova
sayıya bağlandı · "unknown dosyaya yazılıyor" notu → 5 girdilik zorunlu sentetik
test · "hardcode ederse KALDI" niyeti → M2 mutasyonu + 47/51 tam-tablo testi +
korpusta olmayan 6 ülke · kabul komutu 7 yol için bayt kapısı aldı, `GATES-OK`
olmadan geçmez · test eşiği yoktu → ≥47 · tek cümlelik mutasyon → adı konmuş 3
mutasyon · `+N` ve `remote=False` tanımsızdı → karara bağlandı ve testle kilitlendi.

**S4'E YAZILI BORÇ (S3'ten devredildi):** taşınamayan profil için `global` dışı
scope elenir; `unknown` elemesi `remote_scope_unknown` diye AYRI isimlendirilir.
Ayrıca hakemin bulduğu bağımsız hata: `match.py:123` profil ülkesini location
string'inde arıyor (`"turkey" in location`) — Ankara profili için hiçbir ilanda
tutmaz. S4 bunu görmezse `remote_scope` düzelse bile skor tarafı yanlış kalır.

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

### ⚠ S4 KARTI — HAKEM YENİDEN YAZDI (KART YANLIŞ). Eski kart ÖLÜ.

```
ÖLÜ KART:
KABUL KOMUTU : python3 -m unittest discover engine/tests && python3 engine/match.py profile.json --stats
EŞİK         : kalan eşleşmelerin %100'ü global remote ya da profil ülkesinde ·
               yeni kuralın tetiklenme sayısı > 0 · farklı profille de doğru eliyor
DOKUNULABİLİR: engine/match.py, engine/tests/
```

**Bugünkü ölçüm — ürünün utandırıcı gerçeği.** `match.py profile.json --stats`
bugün 142 eşleşme veriyor. Hakem bu 142'nin scope dağılımını saydı:
`None` (uzaktan değil) 115 · `country:US` 13 · `global` 9 · CA 2 · DE 2 · IN 1.
**Damla'ya yollanan 142 ilanın 133'ü başvuramayacağı iş.**

**Neden ölü:**

1. Madde 2 **var olmayan alana** dayanıyordu. `profile.json`'da `relocation`
   boolean'ı YOK; olan `constraints.relocation_now` serbest metni. Profil ülkesi
   de yapılandırılmamış (`identity.location: "Ankara, Turkey (Bilkent University)"`).
   Üstelik `profile.json` DOKUNULABİLİR listesinde değildi → uygulanamaz kart.
2. **Madde 1 kırılamaz kapıyı kırmayı emrediyordu.** Hakem `us_work_auth`'u
   kaldırılmış bir kopyada miras testleri koştu: **4 test kırılıyor**
   (`us_auth_excluded_for_non_us` KeyError; `ms_penalty_not_exclusion`,
   `reasons_are_english_and_scored`, `stale_penalty` — bu üçü fixture'ı
   `Remote - USA` olduğu için yeni geo kuralına takılıyor).
   **Madde 1 REDDEDİLDİ:** `us_work_auth` kalıyor. Teşhis ("ölü kod") doğru,
   tedavisi silmek değil — yanına gerçekten eleyen kuralı koymak.
3. Kural sadece `remote_scope`'a dayansaydı korpusun %94'ünü oluşturan **425
   yerinde ilana hiç dokunmazdı**; Damla'ya 124 ulaşılamaz ilan kalırdı.
   Yerinde-ilan kolu kartta YOKTU.
4. Tek `unknown` ismi iki ayrı parse borcunu gizliyordu: uzaktan-scope okunamayan
   (**0**) ve konum-ülkesi okunamayan (**34**).
5. "%100'ü global ya da profil ülkesinde" eşiği **0 eşleşmeyle de sağlanır.**
   Sayı yoktu.
6. Karşı-profil tanımsızdı. Kabul komutu byte kapılarını içermiyordu.

### YENİ KART — YÜRÜRLÜKTE

```
KULLANICI CÜMLESİ : Bana gelen her ilana gerçekten başvurabiliyorum.

İŞ:
1. profile.json → `constraints` altına EKLE: "relocation": false, "home_country": "TR".
   `relocation_now` serbest metni KALIR. Başka satıra dokunma (çalışma ağacındaki
   CV düzeltmesi dâhil — o Damla'nın, geri alma).
2. engine/fetch/common.py → SADECE EKLEME: `listing_country(location) -> "XX"|"unknown"`
   saf fonksiyonu; oradaki COUNTRY_CODES / US_STATE_CODES / PLUS_N_RE tablolarını
   kullanır. FIELDS, record(), parse_markdown_table DEĞİŞMEZ.
   Ayrıca COUNTRY_CODES'a "turkey": "TR" eklenir (bugün tabloda YOK).
3. engine/match.py:
   - us_work_auth KALIR, sırası değişmez, stats anahtarı korunur.
   - `country = "turkey" if ...` hack'i (satır 148) ve `country in location`
     (satır 123) kalkar; yerine listing_country(job) == home_country ile
     +3 "location fits".
   - home = constraints.home_country YALNIZCA constraints.relocation is False ise
     okunur; aksi halde None ve kural KAPALI.
   - home doluysa, phd/mba/us_auth'tan SONRA, puanlamadan ÖNCE:
       remote_scope == "global"              → geç
       remote_scope == "unknown"             → remote_scope_unknown
       remote_scope == "country:XX", XX≠home → remote_scope_country_mismatch
       remote_scope is None + listing_country == "unknown" → location_country_unknown
       remote_scope is None + ülke≠home      → onsite_abroad
   - relocation:false beyan edilmiş ama home_country yoksa → sessiz geçme YOK,
     SystemExit ile isimli hata.
   - --stats her isimli kovayı basar (0 olanlar dâhil) + kural durumunu
     ("geo rule: on, home TR" / "off, profile declares no relocation constraint")
     + matched.
   - ÇIKMAZ SOKAK: matched == 0 ise --stats en büyük eleme kovasını adıyla yazar
     ve match.py exit code 1 döner.
4. engine/tests/test_geo_reach.py (YENİ dosya; test_engine.py'ye DOKUNMA).

KABUL KOMUTU:
python3 -m unittest discover engine/tests && python3 engine/match.py profile.json --stats && test -z "$(git status --porcelain docs tools engine/data/jobs.json engine/tests/test_engine.py)" && test "$(git hash-object engine/data/jobs.json)" = ad8a4e643f18fa36b11a24669d5cfbcc255a3683 && test "$(git hash-object engine/tests/test_engine.py)" = 6bbd4a51a5bff32c202051d8e0f9a1f530929cfe && test "$(git rev-parse HEAD:docs)" = 80281d148a47de0e79e32d3344d6fd7d052a500c && test "$(git rev-parse HEAD:tools)" = 6f05c867f87b4ff3d9ab90ccdb5e79cb606eac9f

EŞİK — her sayı hakemin ÖLÇTÜĞÜ sayı:
1.  Miras test_engine.py 15/15 yeşil, blob'u değişmemiş. Toplam test ≥70, 0 hata.
2.  profile.json ile matched TAM 9; dokuzunun da remote_scope == "global" olduğu
    testle kanıtlı.
3.  --stats kovaları TAM: phd_only 51 · mba 2 · us_work_auth 0 · onsite_abroad 339 ·
    remote_scope_country_mismatch 18 · remote_scope_unknown 0 ·
    location_country_unknown 34 · no_signal 0; kovalar + matched = 453.
4.  Yeni kuralın tetiklenmesi: 339+18+0+34 = 391 > 0 (eski kural 0'dı).
5.  Karşı-profil US-taşınamaz: matched TAM 144, onsite_abroad 217, mismatch 5,
    hayatta kalanların %100'ü global ya da listing_country == "US".
6.  Karşı-profil ZZ-taşınamaz (var olmayan ülke): matched TAM 9, TR ile aynı
    kovalar → 9'un ülkeden değil global'dan geldiği kanıtlı.
7.  Taşınabilir profil (relocation:true): matched TAM 142, dört yeni kova 0,
    --stats kuralı "off" yazar.
8.  Beyan kilidi: gerçek profile.json'da constraints.relocation is False ve
    home_country 2-harfli ISO — test bunu kilitler (alan silinirse KIRMIZI).
9.  Eksik home_country (beyan var, kod yok) → isimli SystemExit, sessiz geçiş yok.
10. Çıkmaz sokak: global remote içermeyen sentetik ilan listesi + taşınamaz profil
    → matched 0, --stats en büyük kovayı adıyla basar, exit code 1.
11. MUTASYON: faz öncesi match.py'ye karşı 2., 5. ve 6. maddenin testleri KIRMIZI
    düşer (bugünkü değerler 142 / 142 / 142). Kanıt çıktısıyla raporlanır.
12. common.py diff'i yalnızca EKLEME; S2 replay testleri
    (test_replay_is_byte_identical, test_replay_dedupe_order_is_identical) yeşil.

DOKUNULABİLİR: engine/match.py · engine/tests/ (YENİ dosya; test_engine.py DEĞİL) ·
engine/fetch/common.py (sadece ekleme) · profile.json (sadece constraints altına
iki alan ekleme)
```

**Hakemin zorlaştırdıkları:** "%100'ü global/ülkede" (0 ile de sağlanır) → **matched
tam 9** + kova kova tam sayı + 453 denkliği · "tetiklenme > 0" → **391**, dört isimli
kova · "farklı profil dener" (tanımsız) → **üç ölçülmüş karşı-profil** (US=144, ZZ=9,
taşınabilir=142) · kural sadece remote → 425 yerinde ilanı da kapsıyor · tek `unknown`
→ iki ayrı borç · çıkmaz sokak → testli + exit 1 · kabul komutu → 4 byte kapısı
(blob/tree hash) · `profile.json` listeye girdi, beyan testle kilitli.

**Hakemin ayrıca bulduğu, S4'ün işi OLMAYAN iki şey:**
- `+3 "location fits"` düzeltilince US profilinde `no_signal` 258 → 0 düşüyor
  (144 vs bonussuz 74). Yani hiç ilgi/beceri eşleşmesi olmayan ilan sırf ülkende
  diye eşiği geçiyor. **Puanlama eşiğinin ayrı zayıflığı.** TR profilinde etkisi
  sıfır (korpusta TR ilanı 0) ama başka profil eklenirse patlar. Ayrı kart konusu.
- Korpus ülke dağılımı (425 yerinde ilan): US 155 · SG 38 · GB 22 · NL 21 · DE 20 ·
  CA 16 · FR 14 · HK 11 · ES 10 · BR 8 · IN 7 · bilinmeyen 34 · **TR 0**.
  Damla'ya ulaşan tek kanal global remote ve o kanal **9 ilan** geniş.
  Bu bir ürün kararı gerektiriyor (kaynak eklemek), kod hatası değil. → S14.

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

```
## S3 — Remote dediğim remote — GEÇTİ (kart hakem tarafından bir kez yeniden yazıldı)
ölçülen: 63 test yeşil (36 → 63, +27 yeni) · faz-öncesi 27/27 kırmızı
         · common.py +141/-0 → FIELDS ve record() bir harf değişmedi (numstat kanıtı)
         · census jobs.json {global:9, US:14, CA:2, DE:2, IN:1, unknown:0} = 28 remote
         · census fixtures {global:3, US:14, CA:1, BE:1, DE:1, HK:1, unknown:0} = 21
           — hakem ikisini de KENDİ ayrıştırmasıyla saydı, birebir tuttu
         · tablolar: 47 ülke + 51 ABD kodu, ŞEHİR ANAHTARI YOK, LATAM/EMEA/APAC YOK
         · mutasyon M1 → 10 test, M2 → 6 test (D ve G düştü, anti-hardcode gerçek),
           M3 → 3 test (E düştü)
         · census testleri TAM SÖZLÜK assertEqual, 47/51 gerçekten liste geziyor
         · run() özeti gerçek census, unknown sıfırken bile ekranda
eşik:    ≥47 test · GATES-OK · iki korpusta tam sözlük eşitliği · 3 mutasyon
birikimli: S1 exit 0 · S2 exit 0 · REPLAY hakemin kendi koşusunda hâlâ BYTE-EŞ
         (5c5495bc…, S3 common.py'ye dokunduğu hâlde kırılmadı — ekleme saf)
hakem notu: Kural gerçekten kural — tabloyu kısınca anti-hardcode kapısı kızardı,
         yani 47/51 korpusa fit edilmiş liste değil, ve unknown sessiz default'a çökmüyor.
```

**S3'ün bıraktıkları:**
1. **KART NOT HATASI (kayda geçti, KALDI değil):** kart fixtures dedupe'lu setini
   540 diye yazmıştı; gerçek **599**. Census sözlüğü tuttuğu için faz düşmedi.
2. **⛔ S1 KAPISI KIRMIZI BİR İNVARYANT TAŞIYOR.** `tools/measure.py --invariants`
   D9'u KIRMIZI (1 ihlal, `build_site.py:627`) raporluyor ama komut yine de
   **exit 0** dönüyor. Yani birikimli kapı D9'u BLOKLAMIYOR. Sahibi S5; S14'ün
   "D1-D9 dokuzu da yeşil" eşiği bunu kapatmadan tutmaz.
3. `tools/measure.py:112 country_of()` aynı işi eksik yapan İKİNCİ bir lokasyon
   kuralı: ülke *adı* döndürüyor, `anywhere`/`worldwide`'ı dünya-geneli sayıyor
   (yani TAHMİN ediyor — S3'ün yasakladığı şey). `test_fetch.py:331` buna bağlı.
   `tools/` donduğu için birleştirilemedi. Açık madde.
4. `"Remote - Anywhere"` bilerek `unknown`. Korpusta 0 örnek var, bugün kimseyi
   etkilemiyor; kaynak yarın bu formatı basarsa Damla'nın başvurabileceği ilan
   `global` yerine `unknown` kovasına düşer. Bilinsin.
5. **Kullanıcının şikâyeti HENÜZ DÜZELMEDİ.** S3 yalnız ayrımı yapan ölçümü
   kurdu; eleme `match.py`'de ve o S4'ün işi.

```
## S4 — Alamayacağım işi yollamıyor — DURDU (hüküm verilmedi, hakem koşulamadı)
ölçülen: 92 test (63 → 92, +29 yeni), 91 yeşil 1 KIRMIZI
         · faz-öncesi 12 yeni test kırmızı düştü
         · TR (gerçek profile.json): matched 142 → 9 · geo rule: on, home TR
           kovalar: phd_only 51 · mba 2 · us_work_auth 0 · onsite_abroad 339 ·
           remote_scope_country_mismatch 18 · remote_scope_unknown 0 ·
           location_country_unknown 34 · no_signal 0 · toplam 453 ✓
         · ZZ-taşınamaz: matched 9, kovalar TR ile bit bit aynı ✓
         · taşınabilir: matched 142, dört yeni kova 0, kural "off" ✓
         · US-taşınamaz: matched 140 ✗ (eşik 144 diyor)
         · mutasyon: beyan çıkarılınca 142/142/142'ye dönüyor, üç test kırmızı ✓
eşik:    5. madde dışında hepsi tuttu
hüküm:   YOK. Hakem doğrulama koşamadı — rabadon red-base tüm Bash'i blokluyor.
```

**S4'ün ajanının kart dışında yapmak ZORUNDA kaldığı tek değişiklik.**
`engine/tests/test_fetch.py:39-47` — S2'nin DeathGate kurbanı TikTok "AI Infra
Engineer Intern" `San Jose, CA` idi. Yeni geo kuralı onu `onsite_abroad` diye
eliyor, yani canlıyken de ölüyken de maile girmiyordu → S2'nin
`test_mail_does_carry_the_same_listing_while_it_is_alive` ve
`test_gate_removal_breaks_both_mutations` testleri **boşa düşüyordu.**
Kurban, testin kendi docstring'inin istediği şeye çevrildi: Astreya
"AI Infrastructure DC Design Intern", `location: "Remote"`, skor 5.
Test mantığı değişmedi, yalnız veri seçimi. Hakem bunu ayrıca denetlemeli.

**S4'ün ortaya çıkardığı, kartın işi olmayan gerçekler:**
1. **Damla'nın günlük maili pratikte 3 ilan.** `--min-score` varsayılanı 5;
   hayatta kalan 9 eşleşmenin yalnız 3'ü (skor 7, 5, 5) o eşiği geçiyor,
   kalan 6'sı 1-3 arası. Kartta bu yoktu.
2. **Dokuz hayatta kalanın hiçbiri Damla'nın hedef alanı değil.** Astreya,
   Boston Medical Center, OpusClip, Ensemble Health, Hone Health, Ancestry ×2,
   Whiterabbit.ai, Vocal Media. Kural "başvurabilir mi"yi çözdü,
   **"istiyor mu"yu çözmedi.** → S14'ün kaynak açığı raporuna.
3. **Yeni kural canlı siteyi ve maili doğrudan vuracak.** `build_site.py` ve
   `send_mail.py` gerçek `profile.json` ile `match.run` çağırıyor; bir sonraki
   build'de sitedeki sayı 142'den **9**'a düşer. `docs/` bu fazda donduruldu,
   build koşulmadı. `CLAUDE.md`'deki "453/142/41" sayıları da eskiyecek.
4. `location_country_unknown` 34 ilan sessizce eleniyor; içlerinde gerçekten
   başvurulabilir iş olabilir. İçeriklerine bakılmadı. **DOĞRULANMADI.**

```
## S4 — Alamayacağım işi yollamıyor — GEÇTİ
        (kart hakem tarafından yeniden yazıldı; eşik Damla onayıyla bir kez
         düzeltildi ve aynı anda zorlaştırıldı)
ölçülen: 107 test yeşil (92 → 107), 0 kırmızı · miras test_engine.py 15/15,
         blob 6bbd4a51 değişmemiş · GATES-OK
         · canlı TR: matched 142 → 9, dokuzunun da remote_scope == "global"
           (hakem 9/9'u KENDİ hesabıyla doğruladı)
         · kovalar: phd_only 51 · mba 2 · us_work_auth 0 · onsite_abroad 339 ·
           country_mismatch 18 · scope_unknown 0 · location_country_unknown 34 ·
           no_signal 0 → 444 + 9 = 453 ✓ (hakem kendi topladı)
         · ZZ-taşınamaz: kovalar TR ile HARF HARF aynı → 9'un global'dan geldiği,
           Türklükten gelmediği kanıtlı
         · US-taşınamaz: 140 · onsite_abroad 217 · mismatch 5 · no_signal 4
         · taşınabilir: kural "off", dört kova 0, matched 142
         · matched==0 senaryosu: "dead end: onsite_abroad (31)", exit 1 ✓
         · home_country eksik → isimli SystemExit, exit 1 ✓
         · mutasyon: beyan silinince matched 142'ye döndü, 13 geo testi kırmızı
         · common.py +27/−0 (FIELDS/record/parse_markdown_table dokunulmadı)
         · profile.json: yalnız iki alan eklendi; Damla'nın commit'lenmemiş
           CV düzeltmesi yerinde, dokunulmadı
birikimli: S1 exit 0 · S2 exit 0 · REPLAY hakemin kendi koşusunda BYTE-EŞ (5c5495bc…)
hakem notu: Dokuz eşiğin dokuzu hakemin kendi sayılarıyla tuttu; worktree kanıtı ve
         küçülen-korpus simülasyonu ajana güvenilmeden yeniden üretildi.
```

**S3'ün byte kapısı ile S4'ün işi çelişti — hakemin kararı.**
S3'ün kabul komutu `engine/match.py`'nin değişmemesini istiyordu; S4 kartı onu
DOKUNULABİLİR ilan edip değiştirmeyi zorunlu kılıyordu.
**Hüküm: S3'ün `match.py` maddesi S4 için DÜŞER, koşu DURMAZ.** Gerekçe: o kapı
S3'ün kendi teslimatını koruyan **faz-yerel** bir dondurmaydı, kalıcı yasa değil.
Bir sonraki fazın kartı önceki fazın faz-yerel dondurmasını açabilir — açamasaydı
hiçbir dosya bir daha asla düzelemezdi. Diğer 6 yol donmuş kaldığı ölçüldü.

**İŞ 1 — eşik düzeltmesi (Damla onayladı) ve aynı anda zorlaştırma.**
`144` hatalı türetmeydi: geo elemesinden SAĞ ÇIKAN sayı (453−309), `matched` ise
puanlamadan SONRAKİ sayı. Aradaki 4 TikTok "ML Engineer Intern" ilanı puanlamada
`no_signal`'a düşüyor. **Hakem `git worktree` ile `a9b66ba`'yı kendi açtı ve
dördünün faz ÖNCESİNDE de `no_signal` olduğunu çalıştırarak gösterdi** — hem
`country='turkey'` hem `'usa'`, hem `auth=False` hem `True` altında.
S4 hiçbir ilanı öldürmedi. Karşılığında eşik zorlaştı: `matched` sabiti +
`no_signal == 4` + dört ilan İSİM İSİM literal + "bütün kova bu dördü" kanıtı.

**İŞ 2 — testler canlı korpustan söküldü.**
Canlı `jobs.json`'a çivili kesin sayı KALMADI (hakem üç dosyayı tek tek taradı).
Eski çiviler (453, 41, 42, census 9/14/2/2/1) donmuş fixture'a taşındı ve
fixture'dan hesaplandığı hakem tarafından yeniden üretildi. Canlıya bakan her
şey artık tip/şekil invaryantı: kova toplamı == considered · negatif kova yok ·
hayatta kalanların %100'ü ulaşılabilir · matched ≥ 0 · çift kayıt yok ·
ledger == alive.
**Hakemin kendi simülasyonu:** korpus %50'ye (226) ve %10'a (45) indirildi →
ajanın üç dosyası **%10'da bile yeşil.**

**⛔ AMA İŞ 2'NİN HEDEFİ TAM TUTMADI — A5.** Hakemin simülasyonunda her iki
küçültmede de TEK bir test kızarıyor: `engine/tests/test_engine.py:29`
`assertGreater(strong["matched"], 200)` (162 ve 34 geldi). O dosya ajana
yasaklıydı, **ajanın suçu değil**, ama koşu için gerçek risk:
`daily.yml` testleri `send_mail.py`'den ÖNCE koşuyor. Bugün 323/453, %40 pay;
**sabah fetch'i ~273 ilanın altına düşerse mail ölür.** Ajan bunu örtmedi,
A5 olarak yazdı. Kartsız açık madde.

**Hakemin bulduğu tek yumuşak nokta:** `test_geo_reach.py:258-264` yorumu CANLI
korpusun dört TikTok ilanını anlatırken hemen altındaki `US_NO_SIGNAL` listesi
FIXTURE korpusun dört FARKLI ilanını sayıyor. İkisi de doğru, hakem ikisini de
ayrı ölçtü, ama yan yana yanıltıcı okunuyor. Kayda geçti.

---

## S5a · "KAÇIŞ KAPISI SAĞLAM"

Damla S5'i ikiye böldü: **"kaçış kapısı kırıkken yeni sayfa üretmek ihlali
çoğaltır."** Kişisel sayfa S5b'dir, bu kartın işi değildir.

### Hakemin ölçümü — taslak 1 ihlal diyordu, gerçek 4

| dosya:satır | bağlam | sorun |
|---|---|---|
| `build_site.py:627` | `<script>` JSON | `json.dumps` ham basılıyor, `</script>` kaçışı yok — measure.py'nin gördüğü TEK ihlal |
| `build_site.py:291` | `href` | `esc()` tırnağı kaçırıyor ama **şemayı kaçırmıyor** → `javascript:` geçiyor |
| `build_site.py:594` | `href` | aynı |
| `build_site.py:632` | `href` | aynı |

24 basma noktasının 20'si doğru. `send_mail.py` düz metin üretiyor, D9 kapsamı dışı.

### SÖMÜRÜ — hakem sandbox'ta gerçekten koşturdu

İlan başlığına payload konup `build_site.py` koşuldu, çıktı gerçek HTML parser
ile ayrıştırıldı. **Her ilan sayfasında dört ayrı çalıştırılabilir yol:**

```
script #2  body='alert(1)'                          <-- ÇALIŞIR
script #3  body='alert(4)'                          <-- ÇALIŞIR
img        {'src':'x', 'onerror':'alert(2)'}        <-- ÇALIŞIR
href       "javascript:alert(3)"                    <-- ÇALIŞIR
```

`docs/jobs/index.html`'de de `javascript:` href canlı.

### ⛔ KAPI D9'A ÖZEL DEĞİL — measure.py'nin TAMAMI KIRIK

`tools/measure.py:679-706`: `cmd_invariants()` sayıları **döndürüyor ama
`main()` onları ATIYOR.** Dosyadaki tek `sys.exit` "hiç alt komut verilmedi"
hâli için. Sonuç:

- D9 kırmızı → exit 0 · D4/D5/D6 kırmızı olsaydı → **yine exit 0**
- `--unconfirmed` bugün **"ONAYSIZ ADRESE GONDERIM: 1"** basıyor → exit 0
- `--double-send` "YAPISAL BULGU SAYISI: 2" basıyor → exit 0

**S1'den beri her fazın "birikimli kapısı" hiçbir şeyi tutmuyordu; komut yalnız
ekrana yazıyordu.** S5a D4/D5/D6/D9'u bağlar; D1/D2 bilinçli dışarıda (D2 bugün
1, kart kendi dışındaki bir kusurdan kilitlenmemeli) → **A10 açık maddesi.**

### mock-contract çatışması — hakemin çözümü

"Yalnız yeni fonksiyon" şartı lafzıyla imkânsız (çağrılmayan fonksiyon hiçbir
şeyi kapatmaz). Hakem şartın **ruhunu makine kontrolüne** çevirdi: 2 yeni
fonksiyon + 5 çağrı satırının yeniden bağlanması, ve iki sayılabilir kapı —
(a) `build_site.py`'deki hiçbir string `Constant` literal'i değişmez (`ast` ile
doğrulanır), (b) 5 yüzeyin sha256'sı sabit. **Kilit "güven bana" ile değil,
2.096.716 baytlık ölçümle açılıyor.**

Ayrıca ölçüldü: taslağın "docs/ bugünkü hâliyle byte-eş" şartı **düzeltme
olmadan da tutmuyor** — commit'teki `docs/` 27 Tem tarihli, bugün koşturunca
462 dosyanın 460'ı zaten farklı (tarih sabitleri + S3/S4 geo kuralı 142→9).
A/B ölçüldü: düzeltme öncesi/sonrası **462 dosya, 0 fark, 0 bayt.**

### D9'un altı bağlamı — tek `esc()` kuralı D9'u KAPATMAZ

| bağlam | kural | bugün |
|---|---|---|
| gövde metni | `esc()` = `html.escape(quote=True)` | 20 sink, doğru |
| attribute | aynı `esc()`, farklı hata modu (tırnak kırma) | 2 sink, doğru |
| `<script>` JSON | **`esc()` BURADA YANLIŞ**, JSON'u bozar → `json_in_html`: `< > U+2028 U+2029` → `\uXXXX`, **`&` DOKUNULMAZ** (99 yerde geçiyor, bayt kapısı) | **1 sink, KIRIK** |
| URL/`href`/`src` | **`esc()` YETMEZ** → `safe_url()` yalnız `https?://`, sonra `esc()` | **3 sink, KIRIK** |
| XML `<loc>` | `esc()`, girdi `slugify`'dan geçmiş | 1 sink, doğru |
| inline JS/CSS | **YASAK**, dış metin hiç girmez | 0 sink, sayaç 0'da kalmalı |

### KART — YÜRÜRLÜKTE

```
KULLANICI CÜMLESİ : Sitede gördüğüm hiçbir metin bana kod çalıştıramaz.

İŞ:
1. build_site.py'ye YENİ json_in_html(data): json.dumps çıktısında < > U+2028
   U+2029 → \uXXXX. & DOKUNULMAZ. job_jsonld (627) tek satırda çağırır.
2. YENİ safe_url(u): yalnız https?:// hayatta kalır, gerisi "". Üç href sink'i
   (291, 594, 632) esc(safe_url(...)) olur; "link var mı" koşulu da safe_url
   üzerinden sorulur. job_jsonld'deki sameAs (622) ve directApply (624) de
   safe_url'den geçer — link düşüp directApply:true kalması tutarsız olur.
3. tools/measure.py main(): --invariants D4/D5/D6/D9'dan HERHANGİ biri > 0 ise
   sys.exit(1). D1/D2 kapıya BAĞLANMAZ (D2 bugün 1, ayrı kart).
4. measure.py D9 tarayıcısı URL bağlamını görecek: FormattedValue'nun hemen
   öncesindeki literal href=/src=/action= ile bitiyorsa ve ifadede safe_url(
   veya slugify( yoksa → ihlal. Motor sabitleri beyaz listeye.
   (Prototiplendi: düzeltme öncesi 7 aday → 3 gerçek ihlal + 4 sabit;
    düzeltme sonrası 4 sabit, 0 ihlal.)
5. engine/tests/test_d9_escape.py — 5 test, altı bağlamdan beşi. Ayrıştırma
   GERÇEK HTML parser ile (html.parser), string `in` araması YASAK
   (`</SCRIPT >` varyantı string aramasını atlatır).
   Payload seti en az: </script><script>alert(1)</script> ·
   </SCRIPT ><img src=x onerror=alert(2)> · javascript:alert(3) ·
   <svg onload=alert(5)> · Ev"il & <b>Co</b> · U+2028
6. engine/tests/test_output_frozen.py — DONMUŞ FIXTURE korpusundan (599 ilan)
   üretilen 5 yüzeyin sha256'sı sabit. TODAY/TODAY_ISO/VERSION 2026-07-27'ye
   sabitlenir, cv_critique.JOBS fixture'a yönlendirilir.
   engine/data/jobs.json'a BAĞLANMAZ — bağlansaydı daily.yml her sabah CI'yı
   kırardı. Ayrıca build_site.py'deki hiçbir string Constant literal'i değişmez.
7. KAPSAM DIŞI: docs/u/<token>.html (S5b), D1/D2 exit kodu, cv_engine_js.py,
   schema.sql.

KABUL KOMUTU:
python3 -m unittest discover engine/tests && python3 tools/measure.py --invariants

EŞİK — her sayı hakemin ÖLÇTÜĞÜ sayı:
· ≥112 test (bugün 107 + en az 5 yeni), 0 fail 0 error. 107'nin hiçbiri kızarmaz.
  test_engine.py blob 6bbd4a51… değişmez, 15/15.
· measure.py --invariants: D4=0 D5=0 D6=0 D9=0, dördü YEŞİL, çıkış kodu 0.
· KAPI MUTASYONU: json_in_html çağrısı çıkarılınca → D9 ≥ 1 VE çıkış kodu 1.
  (Bugün aynı mutant D9=1 basıp exit 0 dönüyor — kapının onarıldığının kanıtı budur.)
· TARAYICI MUTASYONU: 291/594/632'den HERHANGİ birinden safe_url çıkarılınca →
  D9 ≥ 1, çıkış kodu 1. (Bugünkü tarayıcı üçünü de sessizce geçiriyor.)
· KAÇIŞ MUTASYONU: hakem koşturdu, düzeltilmemiş koda karşı 3/3 KIRMIZI:
    AssertionError: 'alert(1)' unexpectedly found ... payload executes as JS
    AssertionError: [('img','onerror','alert(2)'), ('a','href','javascript:alert(3)')] != []
    JSON-LD gövdesinde '</' bulundu
  Düzeltme uygulanınca 3/3 YEŞİL.
· BAYT DONMASI (fixture korpusu 599, tarih 2026-07-27 sabit) — fark 0:
    index        8 792 B  6d0f7ceee3224519504355b928062eda1d21927210d59c07cd8b51c56607441c
    cv           9 295 B  d2de8c1c76e9fee8762dfd69bbdda4f3e95ffb34d162441273bec455621ba6c2
    jobs_index 265 046 B  ba8a9b5ec6a02b825394ed7533822c0b7de995ccccb296053d589269b8d74b52
    job_pages 1811 188 B  7cf10d770a0e5bec5ef2f4e56b10a491f6b83e0309f8ed18d3b55c83fd964165
    unsubscribe  2 395 B  a995b6d1c6613b2031d4672eab9a0a7f24d92b7bec1257c45da74c23a57152b9
    TOPLAM 2 096 716 BAYT
· build_site.py string Constant literal'lerinin çok kümesi DEĞİŞMEZ.
· Ağ 0 çağrı, harici pip paketi 0.

DOKUNULABİLİR:
· engine/build_site.py — yalnız 2 yeni fonksiyon + 5 çağrı satırının yeniden
  bağlanması (622, 624, 627, 291, 594, 632). Şablon literal'i, CSS, JS sabiti,
  gövde metni DEĞİŞMEZ.
· tools/measure.py — yalnız main() çıkış kodu + D9 tarayıcısına URL kuralı +
  beyaz liste. Diğer alt komutlara dokunulmaz. (Damla'nın açtığı tek istisna.)
· engine/tests/test_d9_escape.py (YENİ), engine/tests/test_output_frozen.py (YENİ)

DOKUNULMAZ: engine/data/jobs.json · engine/tests/fixtures/* ·
engine/tests/test_engine.py · match.py · fetch/ · send_mail.py · schema.sql ·
cv_engine_js.py · docs/ · site-mock/ · .github/workflows/daily.yml
```

**Hakemin zorlaştırdıkları:** 1 ihlal → **4** · "D9 exit≠0" → D4/D5/D6/D9'un
herhangi biri, D1/D2 gerekçeli dışarıda · tarayıcı kapsamı denetlensin (açık
uçlu) → tarayıcı **büyütülecek**, mutasyonla kanıtlanacak · tek mutasyon → **üç**
(kaçış + kapı + tarayıcı) · "kaçış kaldırılınca kırmızı" (iddia) → hakem
koşturdu, **tam fail metni kartta** · "docs/ byte-eş" (ölçülemez) → **5 sabit
sha256, 2.096.716 bayt, fixture'a bağlı** (CI'yı kırmaz) · tek yerde test →
**6 bağlam, 4 kaçış kuralı, 5 test, HTML parser zorunlu** · 107 → **≥112 test**.

### S5a'nın ortaya çıkardığı YENİ açık maddeler

| # | ne | sahibi |
|---|---|---|
| A10 | **measure.py'nin çıkış kodu TÜM alt komutlarda kırık.** `--unconfirmed` bugün "1" basıp exit 0; `--double-send` "2 yapısal bulgu" basıp exit 0. D1 ve D2'nin hiç kapısı yok. S5a yalnız D4/D5/D6/D9'u bağlıyor. | **kartsız** |
| A11 | ⛔ **Yayındaki site bugünkü motorun çıktısı DEĞİL.** Canlı site `matched: 142` gösteriyor, bugünkü motor aynı profil+korpusla **9** üretiyor. `docs/` 34 gün eski (27 Tem). Damla siteyi birine gösterecekse bilmesi gereken şey bu. | **S13** |
| A12 | `build_site.py:304` `FORM_HTML.format(capacity, left)` — `seats.json`'dan **ham** basılıyor, hiç kaçmıyor, measure.py hiç taramıyor. Bugün statik repo dosyası (dış veri değil) ama **Supabase'den beslenmeye başlarsa D9 deliği olur.** | **S6/S13** |
| A13 | `.rabadon/guard.json` `codePaths` yalnız `engine/.*\.(py\|sql)$` — **`tools/` guard'da hiç korumalı değil.** "tools/ dondu" kuralı yalnız kart düzeyinde yaşıyor. | **S14** |
| A14 | `SUPABASE_ANON` anahtarı `build_site.py:28-30`'da gömülü ve HTML'e basılıyor. Anon key zaten publiktir, sızıntı değil — ama **RLS politikalarının gerçekten koruduğu DOĞRULANMADI** (canlı DB'ye bakılmadı). | **S6** |

```
## S5a — Kaçış kapısı sağlam — GEÇTİ
ölçülen: 121 test yeşil (107 → 121, +14 yeni), 0 fail 0 error · eşik ≥112
         · miras test_engine.py 15/15, blob 6bbd4a51… değişmedi
         · measure.py --invariants: D4=0 D5=0 D6=0 D9=0, çıkış kodu 0
         · SÖMÜRÜ (hakemin kendi koşusu, 7 payload × 3 hedef × 3 yüzey,
           gerçek html.parser): fazladan script 0 · on* 0 · javascript:/data:/
           vbscript: 0 · ld+json json.loads ile okunuyor ve ["title"] payload'ı
           KAYIPSIZ dönüyor (7/7)
           Aynı sömürü düzeltilmemiş kodda: exec script 5 · on* 3 · tehlikeli URL 9
         · MUTASYON a (json_in_html → json.dumps): D9=1, exit 1 ✓
         · MUTASYON b (üç href sink'inden ayrı ayrı safe_url çıkarıldı):
           311 → D9=1 exit 1 · 615 → D9=1 exit 1 · 653 → D9=1 exit 1 ✓
         · MUTASYON c (S5a öncesi temiz ağaç + yeni testler): 30 kırmızı
           assertion, 9 ayrı test metodu
         · MUTASYON d (tarayıcı URL kuralı + safe_url birlikte kaldırıldı):
           D9=0, exit 0 → ESKİ TARAYICI ÜÇ ŞEMA DELİĞİNİ HİÇ GÖREMİYORDU.
           Yeni kural süs değil, tek tespit eden şey o.
         · BAYT DONMASI (hakemin kendi ürettiği, fixture 599, tarih sabit): 5/5 TUTTU
           toplam 2 096 716 bayt, fark 0
         · build_site.py string Constant çok kümesi: 353 literal, sha c0477c0e…
           7bbf7af / a68aa0d / 8a2c500'de birebir aynı → tasarım TAŞINMADI
         · test_output_frozen jobs.json'a BAĞLI DEĞİL: hakem canlı jobs.json'u
           20 kayda düşürdü, 4/4 yeşil kaldı → daily.yml'ı kırmaz
         · safe_url AGRESİF DEĞİL: canlı 453 linkin 453'ü, 453 company_url'ün
           453'ü hayatta; donmuş 599'da 599/599. Meşru tek link kesilmiyor.
           Reddettikleri: javascript:/data:/vbscript:, şema-göreli //host,
           baştaki boşluk-tab kaçamakları (allowlist olduğu için java\tscript: de)
birikimli: S1 exit 0 · S2 exit 0 · S3 donmuş yollar yerinde · S4 matched 9,
         kovalar 444+9 = 453 (hakem kendi topladı) · REPLAY 5c5495bc…,
         ÜÇ FAZDIR AYNI
hakem notu: Kapı gerçekten kapı — d mutasyonu eski tarayıcının üç şema deliğini hiç
         görmediğini kanıtladı; sömürü düzeltmeden önce 17 kez çalışıyordu, sonra 0.
```

**S3'ün byte kapısı ikinci kez açıldı — S4 emsali.** S5a `build_site.py` ve
`tools/` yollarını açtı (ikisi de kartında DOKUNULABİLİR). Diğer donmuş yollar
(jobs.json, docs/, test_engine.py, send_mail.py, match.py, fixtures/) yerinde.

**A15 — YENİ AÇIK MADDE, ajan örtmedi, hakem doğruladı.**
Donmuş `job_pages` hash'i **taban slug** ile hesaplanıyor. Donmuş korpusta
599 ilan → 583 taban slug, **16 çakışma**. `main()` bunlara `-2`/`-3` ekliyor,
diskte 599 ayrı dosya yazıyor (üzerine yazma YOK), gerçek disk çıktısı
**1 811 252 B / `2440b749…`** — donmuş `1 811 188 / 7cf10d77…`'den farklı
(fark yalnız canonical URL'deki `-2`/`-3`, 64 bayt).
**Yani donmuş test `main()`'in gerçek çıktısını değil bir VARYANTINI kilitliyor.**
Hafifletici: ajan bunu test docstring'inde açıkça yazdı; kartın sha'ları zaten
bu varyantın sha'ları; canlı 453'lük korpusta çakışma **0**, bugün fark üretmiyor.
**Bağlantılı ön-var olan hata (kapsam dışıydı):** `build_jobs_index` "details"
linkini TABAN slug'a basıyor → çakışan ilanlar yanlış sayfaya gider.
Canlıda 0 satır etkileniyor. **Sahibi: S5b** (ilan sayfası yüzeyine dokunan
bir sonraki faz).

**A16 — hakemin bulduğu yumuşak nokta.** D9 tarayıcısının beyaz listesi İSİM
tabanlı (`^(root|canonical|href)$`). Bugün doğru — `nav()`'daki `href` yalnız
motor literal'i alıyor. **Ama yarın `href` adlı bir değişkene ilan verisi
konursa tarayıcı sessizce affeder.** Sahibi: S14 taraması.

**Not:** `test_output_frozen` docstring'i sabiti "git 9af98b1" diye kaynak
gösteriyor; o commit bu repoda YOK. Sabitin DEĞERİ doğru (`8a2c500`), yalnız
atıf yanlış. Kayda geçti.

**A10 daralttı ama kapanmadı:** `measure.py`'nin `--lifetime`, `--unconfirmed`,
`--double-send` alt komutları HÂLÂ exit 0 dönüyor (hakem tek tek koştu).
Yalnız `--invariants` kapıya bağlandı. D1/D2'nin hâlâ kapısı yok.

---

## ⛔ KOŞU S5b'DE DURDU — MİMARİ DUVAR. DAMLA'NIN KARARI GEREKİYOR.

### Ne bulundu

S5b hakemi kartı kesinleştirirken **fazın vaadini düşürmek zorunda kaldı** ve
sebebi bir kod hatası değil, bir **mimari duvar**:

```
docs/ PUBLIC bir git reposunda. daily.yml her sabah
  git add engine/data docs && git push
yapıyor. docs/u/ altına yazılan HER ŞEY:
  · dünyaya açık bir URL
  · GitHub agac API'siyle SAYILABİLİR (noindex insanı kesmez)
  · git geçmişine girer, silinse bile okunabilir
```

Bu yüzden hakem üç şeyi **ölçerek** reddetti:

1. **`unsubscribe_token`'ı sayfa adı yapmak MUTLAK YASAK.** `schema.sql:21`
   `unsubscribe_token uuid` + `schema.sql:69` `grant execute on
   sightstone_unsubscribe(uuid) to anon`. Token public repoda olursa
   **repoyu okuyan herkes her aboneyi abonelikten çıkarabilir.**
2. **Türetilmiş token da çözmüyor** — bugün zaten bir sızıntı var, aşağıda A17.
3. **Hiçbir entropi gizlilik satın almıyor.** 256 bit `secrets.token_hex` de
   public repoda 4 bit kadar gizli. "Token tahmin edilemez" eşiği public repoda
   ölçülemez değil, **YALAN**.

### Hakemin kartı ne hâle getirdi

`docs/u/matches.html` + `.xml`, **token YOK**, veri kaynağı yalnız `profile.json`
(zaten public olan tek profil). Supabase'e ait tek alan basılmaz, testle kilitli.
Teknik olarak doğru ve dürüst — ama:

### ⛔ ŞEFİN GÖRDÜĞÜ, HAKEMİN GÖREMEDİĞİ: S10 KIRILIYOR

Hakem yalnız kendi kartını görür. S10'un kartı aynen şunu diyor:

> **Sessiz hafta politikası.** Onay mailine tek cümle:
> *"Her sabah güncellenen kendi sayfandan bakabilirsin: <token>"*
> **Token S5'te üretildi, link gerçek.**

**O sayfa artık üretilmiyor.** S5b bir tek sayfa üretiyor: Damla'nınki.
Yani S10'un aboneye vereceği link YOK. S5'in varlık gerekçesi ("kaçırma oranını
bakmak isteyen için sıfıra indirir") **abone için değil, yalnız Damla için**
gerçekleşiyor.

Bu bir **kapsam düşürmesidir, zorlaştırma değil.** §0.2 gereği hakem bunu
yapamaz; koşu durur.

### Damla'nın vermesi gereken karar

Abone başına özel sayfa **public GitHub Pages ile ÇÖZÜLEMEZ.** Üç yol, üçü de
senin kararın — şef seçmez:

| yol | bedeli | S10'a etkisi |
|---|---|---|
| **1. Kişi başına sayfa YOK.** S5b hakemin yazdığı gibi kalır (yalnız Damla'nın sayfası). | Bedava, bugün çalışır. | S10'un "sessiz hafta" cümlesi YENİDEN YAZILIR: sayfa vaat edilmez. Kaçırma oranı abone için düşmez. |
| **2. `docs/` özel bir yere taşınır** (private repo + Pages, ya da başka host). | GitHub Pages private repo'da ÜCRETLİ. Damla'nın kararı PARA YOK → bu yol muhtemelen kapalı. | S10 olduğu gibi kalır. |
| **3. Sayfa statik değil, DB'den okunan bir uç nokta olur** (Supabase RLS + token). | Supabase bedava katmanda var. Ama artık `build_site.py` işi değil, yeni bir yüzey; koşu kapsamını aşar. | S10 olduğu gibi kalır. |

**Şefin önerisi: 1. yol**, ve S10'un kartı buna göre yeniden yazılsın.
Gerekçe: 2 ücretli (Damla'nın kararına aykırı), 3 bu koşunun kapsamını aşıyor ve
S12'nin sert durağını geciktirir. 1. yol dürüst: aboneye olmayan bir şey vaat
etmiyoruz.

### A17 — BUGÜN CANLI OLAN BİR SIZINTI (yeni, acil)

`engine/data/mail_state.json` **commit'li ve public**, içinde `sha1(email)[:12]`
= `bd235c29a8fc` duruyor. **Tahmin edilen bir e-posta adresinin bu servise abone
olup olmadığı offline doğrulanabiliyor.** Bir üyelik oracle'ı. Bugün 1 abone var
(Damla), 200 abonede bu KVKK sorunudur. Kendi kartını hak ediyor.
**Sahibi: kartsız.**

### S5b hakeminin ölçtüğü, karara girmesi gereken diğer şeyler

- **`profile.json` public ve içinde `su.bilge@ug.bilkent.edu.tr` var.**
  Repoda bilerek mi duruyor, bilinmiyor.
- **D9 tarayıcısında ölçülmüş İKİ delik** (hakem deneyle buldu, A16 büyüdü):
  (a) değişken adı filtresi `\b(job|j|r|sub|row)\b` — yeni döngü değişkeni
  `entry`/`m` adlanırsa **kapı sessizce körleşir**;
  (b) `href` adlı bir YERELE URL atamak, `^(root|canonical|href)$` beyaz listesi
  yüzünden URL kontrolünü **bypass ediyor**.
- **A15 kapatılamaz:** çakışan slug'ları düzeltmek `jobs_index` ve `job_pages`
  sha'larını kırar, "5 sha değişmez" kapısıyla çatışır. Hakem borcu **16'da
  çakılan bir tanık testine** bağlamayı önerdi.
- `docs/robots.txt` bugün `Allow: /`; `unsubscribe.html` yalnız meta `noindex`
  ile korunuyor, robots'ta engellenmiş değil.
- `build_site.py:612-613`'te `if True else ""` ölü dal.
- Supabase modundaki mail `pseudo_profile()` (yalnız level+interests) kullanıyor,
  `profile.json` değil. **Sayfa ile mail aynı profili görmüyor** — hakem
  "mailde ne gördüysen o" iddiasını YASAKLADI, doğru.

**S5b ajanı doğurulmadı. S6-S14 koşulmadı.**

---

## S5b KARARI — DAMLA: "devam et" → **1. YOL** (30 Ağu)

Kişi başına özel sayfa YOK. Public GitHub Pages'te gizlilik satın alınamıyor,
2. yol ücretli (Damla'nın PARA YOK kararına aykırı), 3. yol koşu kapsamını aşıp
S12'nin sert durağını geciktiriyor. Sayfa yalnız `profile.json`'dan üretilir.

**S10'A YAZILI BORÇ:** "sessiz hafta" cümlesi YENİDEN YAZILACAK. Onay mailinde
aboneye **sayfa VAAT EDİLMEZ** — olmayan bir şeyi vaat etmek bu koşunun
düzeltmeye çalıştığı hatanın ta kendisi. S10 kartı geldiğinde hakemi bu satırı
görecek.

**Rabadon `watch` moduna alındı** (Damla'nın emri). Kaydediyor, engellemiyor.
Kapılar artık yalnız kartların kabul komutlarıyla tutuluyor.

### S5b KARTI — YÜRÜRLÜKTE (hakem kesinleştirdi)

```
KULLANICI CÜMLESİ : Mail gelmediği günlerde de eşleşmelerime bakabiliyorum —
                    ve mailin eşiğe takılıp göstermediklerini de görüyorum.

İŞ:
1. docs/u/matches.html + docs/u/matches.xml (Atom). Token YOK, gizlilik iddiası
   YOK. Veri kaynağı yalnız profile.json; Supabase'e ait tek alan basılmaz.
2. match.run(profile, jobs) sonucunun TAMAMI, skor eşiği yok. Donmuş fixture'da
   3 kayıt (skorlar 5/3/3), mailin eşiği 1'de kesiyor. Canlıda 9 eşleşme,
   skor≥5 olan 3.
3. Sayfa noindex; robots.txt'e "Disallow: /u/" MEVCUT LİTERAL'E DOKUNULMADAN
   helper ile eklenir; sitemap.xml'de /u/ geçmez; nav() değişmez, hiçbir yerden
   link verilmez.
4. Sayfanın üstünde veri kaynağı açıkça yazılır ("built from profile.json").
   "Mailde gördüğün" iddiası YASAK — Supabase modundaki mail pseudo_profile()
   kullanıyor, sayfa zengin profili kullanıyor, ikisi AYNI DEĞİL.
5. jobs/ linkleri main()'in diske yazdığı GERÇEK slug haritasından gelir
   (A15 borcu miras alınmaz).
6. Yeni HTML metni esc(), yeni URL safe_url()/slugify() SATIR İÇİ, yeni XML
   metni xml_text() (= esc() + XML-yasak karakter süzgeci: #x0-#x8, #xB, #xC,
   #xE-#x1F ve surrogate'lar).
   Dış veri değişkeni `r` ya da `j` adlanır — tarayıcının filtresi
   \b(job|j|r|sub|row)\b, `entry`/`m` adlanırsa KAPI SESSİZCE KÖRLEŞİR.
   root/canonical/href adına atama YASAK — `href` adlı yerele URL atamak
   ^(root|canonical|href)$ beyaz listesi yüzünden URL kontrolünü BYPASS EDİYOR
   (hakem deneyle buldu).
7. Tüm yeni literal'ler NEW_HELPERS'a eklenen yeni fonksiyonların İÇİNDE;
   main() SIFIR literal kazanır.

KABUL KOMUTU:
python3 -m unittest discover engine/tests 2>&1 | tail -3 && python3 tools/measure.py --invariants >/dev/null && python3 engine/build_site.py >/dev/null && test "$(ls docs/u | wc -l | tr -d ' ')" = 2 && ! grep -q "/u/" docs/sitemap.xml && grep -q "Disallow: /u/" docs/robots.txt && grep -q 'name="robots" content="noindex"' docs/u/matches.html && python3 -c "import xml.etree.ElementTree as E;E.parse('docs/u/matches.xml')" && echo S5B-GREEN

EŞİK:
· 121 mevcut testin HEPSİ yeşil; toplam ≥133 (en az 12 yeni). test_engine.py
  blob 6bbd4a51… değişmez, 15/15.
· Donmuş 5 sha BİREBİR AYNI; altıncı yüzey (user_page) sha'sı çakılır,
  FROZEN_TOTAL_BYTES = 2096716 + yeni yüzey.
· Literal kapısı c0477c0e9fcd184e3ba59450f7e721e56674fef44c25f3d715c36d9f89f984f5
  değerinde kalır; main()'in literal çok kümesi değişmez (AYRI test).
· measure.py --invariants: D4/D5/D6/D9 = 0, exit 0.
· docs/u/ TAM 2 dosya; build_site.py'de supabase|subscriber|mail_state|send_mail
  GEÇMİYOR (testle kilitli).
· Sayfadaki kayıt sayısı == len(match.run(...)) ve fixture'da skoru 5'in altında
  EN AZ 1 kayıt var (eşiksizliğin kanıtı).
· Çakışma zorlanmış korpusta sayfadaki her jobs/ href'i diskte VAR OLAN dosyaya
  çözülür; A15 tanığı fixture'da == 16 çakışma.
· MUTASYON (üçü de zorunlu, hakem deneyle doğruladı):
  1. Yeni fonksiyondan tek bir esc( silinince → measure.py --invariants exit 1
     VE kaçış testi kırmızı
  2. Yeni fonksiyonlar NEW_HELPERS'tan çıkarılınca → literal kapısı kırmızı
  3. main()'e tek string literal eklenince → kapı kırmızı
· XSS: başlığı <script>alert(1)</script> olan ilanla kurulan sitede
  docs/u/matches.html içinde çalıştırılabilir script YOK; matches.xml
  xml.etree ile parse edilir. Başlıkta \x0b varken de feed parse edilir.

DOKUNULABİLİR: engine/build_site.py (yalnız yeni fonksiyonlar + main()'de
literal İÇERMEYEN çağrılar + robots satırının helper ile uzatılması) ·
engine/tests/* · docs/ çıktıları
DOKUNULMAZ: engine/data/jobs.json · engine/tests/fixtures/* · engine/match.py ·
engine/fetch/ · engine/send_mail.py · engine/schema.sql · tools/measure.py ·
.github/workflows/daily.yml
```

```
## S5b — Kendi sayfam var — GEÇTİ
ölçülen: 147 test yeşil (121 → 147, +26 yeni), eşik ≥133
         · miras test_engine.py 15/15, blob 6bbd4a51… değişmedi · S5B-GREEN
         · build_site.py MEVCUT GÖVDE DEĞİŞMEDİ: 9 yeni fonksiyon, main() yalnız
           iki literal-siz satır aldı, robots literal'i BİREBİR duruyor
           (sonuna helper çıktısı eklendi), nav() değişmedi
         · SAYFA: match.run = 9 kayıt · html.parser <li> = 9 · xml entry = 9,
           üçü EŞİT (hakem bağımsız hesapladı)
           skorlar [1,1,3,3,3,3,5,5,7] → mailin --min-score 5 eşiğinin ALTINDA
           6 KAYIT sayfada. Eşiksizlik kanıtlı.
         · GİZLİLİK: docs/u/* içinde supabase / sightstone_subscribers /
           mail_state / send_mail = 0 · e-posta = 0 · 24+ hex dizisi = 0 · JWT = 0
           sitemap.xml'de /u/ = 0 · robots.txt'te Disallow: /u/ VAR ve eski grup
           bozulmadan duruyor · nav() çıktısında /u/ linki YOK
         · Sayfa mail iddiasını AÇIKÇA REDDEDİYOR: "not a copy of what was mailed
           and does not claim to be", "Nothing here is read from the database"
         · DONMUŞ SHA: hakem index'i fixture'dan KENDİ üretti → 8792/6d0f7cee,
           birebir. Diğer 4'ü yeşil, sha'lar HESAPLANIYOR (gömülü değil).
           Altıncı yüzey çakıldı: user_page 3276/3130070b + feed 1415
         · LİTERAL KAPISI c0477c0e… hakemin kendi hesabıyla aynı.
           SURROGATEPASS HİLESİ YOK — hakem aynı çok kümeyi hem surrogatepass
           hem düz utf-8 ile kodladı, İKİSİ DE AYNI sha'yı verdi. Kapı kandırılmamış.
         · XSS (hakemin kendi koşusu, 7 payload × 7 ilan, gerçek html.parser):
           fazladan script 0 · on* 0 · enjekte img/svg 0 · javascript:/data: 0
           matches.xml \x0b VE \x00 varken bile parse OLDU
         · MUTASYON 1 (esc sil): measure exit 1 + 10 test kırmızı ✓
           MUTASYON 2 (NEW_HELPERS'tan çıkar): literal kapısı kırmızı ✓
           MUTASYON 3 (main()'e literal): iki kapı birden kırmızı ✓
           MUTASYON EK (xml_text süzgeci kaldır): \x0b'li başlıkla feed
           "not well-formed" ile PARSE EDİLEMEZ + 9 test kırmızı ✓
           → XML kapısı SÜS DEĞİL
         · A15 TANIĞI: hakemin kendi sayımıyla fixture'da çakışma == 16.
           job_slug_map main()'in sayacını birebir taklit ediyor; diskte olmayan
           ilan link yerine "no page for this listing" alıyor. Çakışma zorlanmış
           korpusta her href resolve().exists() ile doğrulandı.
birikimli: S1 exit 0 · S2 REPLAY 5c5495bc BYTE-EŞ (legacy modülü gerçekten exec
         ediliyor) · S4 matched 9, 444+9 = 453 · S5a D9=0 exit 0, esc silince exit 1
hakem notu: Kartın tek gerçek çelişkisi kartın kendi içinden geliyor ve daraltılmış
         okuma korumayı zayıflatmıyor — kaynağa ek olarak ÇIKTIYI da taradığı için
         sıkılaştırıyor; geri kalan her eşik, mutasyonlar ve XSS dâhil, tuttu.
```

**KART ÇELİŞKİSİ — hakemin kararı (kayda geçti).**
Kartın "`build_site.py`'de `supabase|subscriber|mail_state|send_mail` GEÇMİYOR"
eşiği, kartın KENDİ donmuş-sha eşiğiyle çelişiyordu. Hakem ölçtü: token'lar
`build_site.py`'nin 27, 28, 290, 394, 588, 589. satırlarında; silmek `index`
(8792/6d0f7cee) ve `unsubscribe` (2395/a995b6d1) sha'larını KIRAR.
**Harfi harfine okuma İMKÂNSIZ.** Hakemin kararı: doğru okuma "yeni fonksiyonların
gövdesinde + `docs/u/` çıktılarında geçmiyor" (AST ile `NEW_FUNCS` gövdeleri +
çıktı taraması). **Bu KOLAYLAŞTIRMA DEĞİL:** (1) dosya-geneli okuma bu fazda
korunabilecek bir şey korumuyor — yasakladığı şey bu fazın hiç dokunmadığı, zaten
public olan katılım formunun anon key'i; (2) daraltılmış test düz grep'in
YAKALAYAMAYACAĞI şeyi yakalıyor: **çıktının kendisini.** Gerçek gizlilik riski
orada. Koşu durmadı.

**Ajanın raporladığı, kartın istemediği tek değişiklik.**
`test_output_frozen.py:102-105` `multiset_sha` encode'u `surrogatepass`e çevrildi;
gerekçe: `xml_text` kaynağındaki `\ud800-\udfff` aralığı tek başına surrogate
literal içeriyor ve düz `encode("utf-8")` `UnicodeEncodeError` atıyordu.
**Hakem bunun kapıyı kandırmadığını KENDİ ölçümüyle doğruladı** — aynı çok küme
iki kodlamayla da aynı sha'yı veriyor.

**Ajanın bildirdiği rabadon olayı (bilgi):** `rabadon-gate` iş ortasında bir kez
`engine/build_site.py`'ye yazmayı `build-site-mock-contract` ile blokladı — kart
o dosyayı DOKUNULABİLİR ilan etmesine rağmen. Ajan hiçbir guard kuralını devre
dışı bırakmadı, kırmızı tabanı korumasız bir dosyada düzeltti, blok kendiliğinden
kalktı. Aynı kural ileride bu dosyada tekrar tetiklenebilir.

---

## S6 · "KOLTUK MATEMATİĞİ TUTUYOR"

### SAĞLIK KONTROLÜ — CANLI. ZEMİN'in tahmini YANLIŞ ÇIKTI.

```
POST https://xjtmqncfhuidctxgthhv.supabase.co/rest/v1/rpc/sightstone_seats
HTTP 200   gövde: {"capacity": 100, "taken": 1}
anon key ile çağrıldı, hiçbir secret gerekmedi.
daily.yml secret'ları: SMTP_USER · SMTP_PASS · SUBSCRIBER_EMAIL · SUPABASE_SERVICE_KEY
```

34 gün hareketsizliğe rağmen proje ayakta. **ZEMİN'in "7 günde duraklatılır ve
uyanmaz" satırı bu proje için ÇÜRÜDÜ.** Faz açıldı.

### ✅ A14 KAPANDI — RLS GERÇEKTEN KORUYOR (hakem ölçtü)

Üretimde anon key ile: `select=*` → **200, gövde `[]`** · `count=exact` →
`content-range: */0` · PATCH/DELETE → 204, 0 satır.
`sightstone_seats()` `taken=1` diyor ama anon **0 satır görüyor** → satır VAR,
GÖRÜNMÜYOR. 204'ler tek başına kanıt olmadığı için hakem yerelde kesin kanıt aldı:

```
set role anon; select count(*)                    → 0   (owner aynı anda 100 görüyor)
set role anon; update …                           → UPDATE 0
set role anon; delete …                           → DELETE 0
set role anon; insert (mail_consent=false)        → ERROR: violates RLS policy
set role anon; insert (consent=true, kvkk=now())  → INSERT 0 1
```

Karta **regresyon testi** olarak girdi.
**Yan bulgu:** masa doluyken consent'siz insert, RLS hatası değil "no seats left"
veriyor — BEFORE INSERT trigger'ı RLS WITH CHECK'ten ÖNCE koşuyor. Güvenlik
deliği değil (doluluk zaten `seats()` ile public), ama hata mesajı sırası bu.

### SQL TEST MOTORU — var, ölçüldü

`psql (PostgreSQL) 15.13 (Homebrew)`, `initdb`+`pg_ctl`+`psql` üçü de mevcut.
Hakem `/tmp`'de geçici cluster kurdu, `schema.sql`'i `ON_ERROR_STOP=1` ile
yükledi, exit 0, `select sightstone_seats()` çalıştı.
**Testler CANLI SUPABASE'E KOŞMAZ** (ağ, secret, üretim kirletme). İki katman:
(a) statik SQL ayrıştırma testleri — koşulsuz, CI dâhil;
(b) davranış/eşzamanlılık testleri — `initdb` bulunduğunda, yoksa `skipUnless`.
Böylece CI'daki 147 yeşil kalır, gerçek yarış Damla'nın makinesinde ölçülür.
(Vanilla PG'de `anon` rolü yok; harness `create role anon` demeli.)

### ⛔ TASLAK YANLIŞ SAYIYORDU — kapasite İKİ değil DÖRT yerde

```
engine/schema.sql:38   (trigger)
engine/schema.sql:52   (seats() json)
engine/data/seats.json
engine/build_site.py:826  (fallback)
+ schema.sql:5 ve :34 yorumlarda → toplam 6 geçiş
```

**Donmuş sha çatışması YOK** (hakem ölçtü): `test_output_frozen.py` kendi
`FROZEN_SEATS={"capacity":100,"taken":1}` sabitini `build_index`'e DOĞRUDAN
veriyor; `seats.json`'u da `schema.sql`'i de okumuyor. Literal kapısı da güvende —
`100` bir **int**, kapı yalnız `str` Constant sayıyor.

### KART — YÜRÜRLÜKTE

```
KULLANICI CÜMLESİ : Koltuk doluysa bekleme listesine giriyorum, biri çıkınca
                    sıra bana geliyor.

İŞ:
1. confirmed_at timestamptz. Kapasite 100 → 200, DÖRT kod yerinde birden
   (schema.sql:38, schema.sql:52, engine/data/seats.json,
    engine/build_site.py:826 fallback) + iki yorum satırı.
2. Cap trigger'ının İLK satırı:
   perform pg_advisory_xact_lock(hashtext('sightstone_seats'))
3. Sayım: unsubscribed_at is null and (confirmed_at is not null or
   created_at > now() - interval '48 hours')
4. Sert bounce → unsubscribed_at yazılır.
5. Bekleme listesi tablosu + davet akışı: koltuk boşaldı → en eski kişiye davet
   → 48 saatte onaylarsa koltuk onun → onaylamazsa sıradakine.
6. ÜÇ TERİMLİ SAYIM:
   boş = kapasite − onaylı − (48s dolmamış onaysız) − (cevap bekleyen davetler)
7. D8: boş koltuk varken kimse bekleyemez. Boş varsa form açık/liste boş; dolu
   ise form kapalı/liste açık. İkisi aynı anda dolu OLAMAZ. Davet döngüsü günlük
   koştuğu için gece boşalan koltukta ≤24 saatlik pencere oluşur — GİZLENMEZ,
   schema.sql başına açık yorum olarak yazılır, kullanıcıya görünen cümlesi
   S13'e devredilir.
8. YENİ — RLS REGRESYON TESTİ: anon rolüyle select/update/delete 0 satır,
   mail_consent=false insert RLS ile reddedilir. (A14 ölçümünü kilitler.)

KABUL KOMUTU:
python3 -m unittest discover engine/tests && python3 tools/measure.py --invariants

EŞİK — her sayı hakemin ÖLÇTÜĞÜ sayı:
· Mevcut 147 test yeşil kalır + yeni testler. test_engine.py blob 6bbd4a51…, 15/15.
· 6 donmuş sha VE FROZEN_SEATS={"capacity":100,"taken":1} DEĞİŞMEZ.
· measure.py --invariants D4/D5/D6/D9 = 0, exit 0.
· Yerel efemeral PG 15.13 cluster'ında, 199 koltuk dolu iken 20 EŞZAMANLI insert
  (her biri: begin; insert; pg_sleep(0.5); commit) → sonuç TAM 200, asla 201.
  ⚠ Hakem bugün kilitsiz şemayla aynı deneyi 99/100 ile koştu: sonuç 119.
  YARIŞ GERÇEK, 19 fazla koltuk. Advisory lock eklenince tam 100.
· Onaysız kayıt 48 saat sonra koltuğu bırakır (saat ileri sarılarak ölçülür).
· Kapasite DÖRT kod yerinde de 200; test bunu ayrıştırarak doğrular.
· Aynı koltuğa iki davet gitmez.
· MUTASYON 1: advisory lock satırı silinince eşzamanlılık testi KIRMIZI
  (kilitsiz koşuda 119 ölçüldüğü için garanti).
· MUTASYON 2: üçüncü terim (bekleyen davetler) çıkarılınca çift-davet testi KIRMIZI.
· MUTASYON 3: dört yerden birinde 200 → 100 yapılınca tutarlılık testi KIRMIZI.

DOKUNULABİLİR: engine/schema.sql · engine/tests/ · engine/data/seats.json ·
engine/build_site.py:826 (YALNIZ fallback int'i, başka satır yok)
DOKUNULMAZ: engine/data/jobs.json · fixtures/* · match.py · fetch/ ·
send_mail.py · tools/ · docs/ · .github/workflows/daily.yml
```

**Hakemin zorlaştırdıkları:** kabul komutuna `--invariants` eklendi · "iki yerde
200" → **dört yerde** (taslak yanlış sayıyordu) · "eşzamanlı 20 insert" varsayımı
→ gerçek motor tanımlandı ve **kilitsiz halde 119 ölçülerek** eşiğin anlamlı
olduğu kanıtlandı, eşik 199→200 kenarına çekildi · bir yerine **üç** mutasyon ·
A14 kapatma testi karta girdi · donmuş sha/`FROZEN_SEATS` dokunma yasağı eşiğe yazıldı.

### S6'nın açtığı yeni maddeler

| # | ne | sahibi |
|---|---|---|
| A18 | ⛔ **`engine/data/seats.json` ÖLÜ VERİ.** Hiçbir kod yazmıyor (grep ile doğrulandı). Sonuç: `docs/index.html` sonsuza kadar **"capped at 100 / 99 seats left"** basıyor; gerçek sayı yalnız JS çalışırsa düzeliyor. **JS kapalı ziyaretçi, bot, RSS okuyucu YALAN görüyor.** S6 kapasiteyi değiştirdiği anda yalan büyüyor. Çözüm `daily.yml`'a "seats.json'u DB'den tazele" adımı ister, o da `SUPABASE_SERVICE_KEY` gerektiriyor → S6'nın yarıçapı dışı. | **S13** |
| A19 | `send_mail.py:43` aboneleri `?unsubscribed_at=is.null` ile çekiyor. S6 `confirmed_at` ekleyince bu sorgu da güncellenmeli, yoksa **onaysız kayıtlara mail gider**. `send_mail.py` S6'nın DOKUNULABİLİR listesinde YOK — bilinçli, çünkü bu **S10'un işi** (D2). Yazılı borç. | **S10** |
| A20 | `mail_state.json` son gönderim 2026-07-27 → günlük Actions ~34 gündür ya koşmuyor ya commit üretmiyor. **DOĞRULANMADI** — Actions koşu geçmişine bakılmadı (`gh` ile bakılabilir). | **S14** |

A12 hakem tarafından **S13'e bırakıldı**, gerekçesi ölçüldü: tarayıcı yarısı
`tools/`'ta (dokunulmaz), kaçış yarısı `build_site.py` yarıçapı dışı, ve
`seats.json` bu karttan sonra da repo-statik kaldığı için D9 deliği **teorik**.

```
## S6 — Koltuk matematiği tutuyor — GEÇTİ
ölçülen: 198 test yeşil (147 → 198, +51: 17 statik + 34 davranış), 0 SKIP
         · miras test_engine.py 15/15, blob 6bbd4a51… değişmedi
         · 6 donmuş sha + FROZEN_SEATS {"capacity":100,"taken":1} DEĞİŞMEDİ
           (test_output_frozen.py diff'i BOŞ, dosyaya hiç dokunulmadı)
         · literal kapıları hakemin kendi AST hesabıyla: c0477c0e… ✓ ab44c922… ✓
           (826'daki değişiklik bir int, string çok kümesi değişmiyor)
         · build_site.py TEK hunk, satır 826, 100 → 200. Başka satır yok.
         · EŞZAMANLILIK (hakemin KENDİ cluster'ı, ajanın harness'ı değil):
           199 dolu + 20 ayrı OS süreci → rows TAM 200, 20'den 1'i commit etti.
           Lock silinip aynı deney → rows 219 (20/20 commit).
           KİLİT SÜS DEĞİL, TEK TUTAN O.
           Toplu insert generate_series(1,300) → "no seats left", tablo 0 satır
           (tüm tx geri alındı). generate_series(1,200) → tam 200.
         · 48 SAAT: onaysız kayıt created_at 49 saat geri itilince taken 1 → 0,
           satır tabloda DURUYOR. Onaylı kayıt 375 gün sonra hâlâ taken=1.
         · ÜÇ TERİM: 200 dolu + 2 bekleyen → run_invites 0. Bounce → taken 199.
           run_invites: 1, sonra 0, 0. Toplam davet 1, sadece en eski (w1).
           Üçüncü terim silinince: 1, sonra 1, 0 → taken 199'da takılı,
           TOPLAM DAVET 2. ÇİFT DAVET GERÇEKTEN OLUYOR.
         · MUTASYON 1 (lock sil) → 3 kırmızı + setUpClass ERROR
           MUTASYON 2 (üçüncü terim sil) → 4 kırmızı
           MUTASYON 3 (dört yerin HER BİRİ ayrı ayrı 200→100) → dördünde de kırmızı
             (trigger → +19 davranış ERROR · seats() json → 9 kırmızı ·
              seats.json → 1 · build_site.py:826 → 1)
           MUTASYON EK (hakemin eklediği, revoke satırları sil) → 2 kırmızı
         · Yeni 50 testin TAMAMI faz-öncesi HEAD şemaya karşı kırmızı
           (11 FAIL + 45 ERROR)
birikimli: S1 exit 0 · S2 REPLAY 5c5495bc BYTE-EŞ · S4 matched 9, 444+9=453 ·
         S5a esc silince exit 1 (kapı sağlam) · S5b docs/u TAM 2 dosya,
         sızıntı grep 0, sitemap /u/ = 0, robots Disallow VAR
hakem notu: Kart neyi ölçmek istediyse gerçekten ölçülüyor — kilit 200/219 farkını
         hakemin kendi cluster'ında üretti, RLS testi vanilya PG'nin sahte-geçme
         tuzağına düşmemek için anon'a grant vererek koşuyor, altı mutasyonun
         altısı da kırmızı.
```

**✅ AJAN GERÇEK BİR GÜVENLİK DELİĞİ BULUP KAPATTI.** PostgreSQL yeni fonksiyona
`EXECUTE`'u **varsayılan olarak PUBLIC'e verir.** Anon'a grant VERMEMEK yetmedi:
`sightstone_mark_bounce` ve `sightstone_run_invites` `security definer` ve anon
ikisini de çağırabiliyordu → **anon herhangi bir abonenin adresini yazıp onu
attırabilir, ya da davet döngüsünü istediği an koşturabilirdi.**
Ajanın kendi statik testi bunu KAÇIRDI (yalnız "grant satırı yok" diye baktı,
yeşil geçti); yakalayan davranış testi oldu. `revoke execute … from public`
eklendi ve testi yazıldı. Hakem doğruladı: 9 fonksiyonun 9'u `security definer`;
`mark_bounce`/`run_invites`/`seats_taken` artık **yalnız postgres**,
anon çağrısı "permission denied".

**Hakemin RLS sahte-geçme tuzağı notu:** vanilya PG'de anon'a tablo grant'ı
verilmezse RLS testi "permission denied for table" ile **yeşil geçip RLS
hakkında hiçbir şey kanıtlamazdı.** Test setUp'ta anon'a grant veriyor — doğrusu
bu, hakem grant'sız da koşup farkı gördü.

### ⛔ HAKEMİN BULDUĞU İKİ GERÇEK DELİK — kartın eşiği dışında ama S10'u KIRIYOR

| # | ne | sahibi |
|---|---|---|
| **A21** | ⛔ **Anon kendi kaydını ONAYLI doğurabiliyor.** `insert … confirmed_at = now()` anon olarak GEÇİYOR (rc=0, confirmed=t). Yani 48 saatlik mail-onay kirası **atlanabiliyor**; uydurma adres koltuğu KALICI tutabilir. **S6'nın "koltuk ancak onaylanınca kalıcıdır" gerekçesi istemci tarafından bypass edilebilir.** Daha kötüsü: **S10'un tüm işi "onay maili → confirmed_at". Bu delik açıkken D2 uygulanamaz.** S10 bunu kapatmadan geçemez: insert politikası `confirmed_at is null` şartı istemeli. | **S10 — zorunlu** |
| **A22** | **Sıra atlama.** Anon `sightstone_waitlist`'e `invited_at`/`invite_expires_at`/`invite_token`'ı KENDİ seçerek satır ekleyebiliyor (insert politikası yalnız `mail_consent` ve `kvkk_accepted_at`'e bakıyor), sonra kendi token'ıyla `accept_invite()` çağırıp koltuğu kapıyor. Hakemin deneyinde `honest@x.test` sırada beklerken `cheat@x.test` koltuğu aldı. Kapasite 200'de tutuyor, kimsenin satırı değişmiyor (bu yüzden KALDI değil) ama **"en eski bekleyene davet gider" garantisi anon tarafından delinebiliyor.** Çözüm: waitlist insert politikasına `invited_at is null and accepted_at is null and dropped_at is null`. | **S10** |
| A23 | `sightstone_enforce_cap()` ve `sightstone_waitlist_guard()` PUBLIC'e EXECUTE'lu kalmış (ACL NULL). Trigger fonksiyonu oldukları için PG doğrudan çağrıyı reddediyor, **sömürülebilir değil** — ama "her security definer fonksiyondan public revoke" kuralının tam uygulanmadığı iki yer. | **S14** |
| A24 | **Canlı Supabase'de DOĞRULANMADI.** Hakem kart gereği üretime hiçbir şey koşmadı; Supabase'in `anon` rolünün varsayılan grant'larıyla bu şemanın nasıl davrandığı bilinmiyor — hakem grant'ları taklit etti. Ayrıca `schema.sql`'in **idempotentliği** (aynı dosyayı iki kez yükleme) ne ajan ne hakem tarafından test edildi. | **S12** (gerçek dünya fazı) |

**Not:** `sightstone_seats()` artık `taken` olarak ÜÇ TERİMLİ sayımı döndürüyor —
site sayacı davet rezervasyonlarını da dolu gösterecek. Kasıtlı (D8), ama
S13'ün göreceği sayı bu.

---

## S7 · "AYNI İLAN İKİ KEZ GELMİYOR"

### Hakemin ölçtüğü gerçek sayı — teşhis doğru, hasar 48

10 abonelik hermetik simülasyon (gerçek `jobs.json`, sahte SMTP, 5.'de kopma):

```
KOŞU 1: u0..u3'e mail GİTTİ (4 abone × 12 ilan), 5.'de koptu
        diskteki abone: 0 · diskteki anahtar: 0
KOŞU 2: 10 abonenin HEPSİNE mail gitti
        u0,u1,u2,u3 İKİNCİ KEZ aldı → 4 × 12 = 48 TEKRAR GÖNDERİM
```

Kök çift: (a) yazım döngüden sonra (`:184`), (b) istisna `finally`'den geçip
yayılıyor, `if mailed:` satırına **hiç ulaşılmıyor**.

### ⛔ KABUL KOMUTUNUN İKİNCİ YARISI VAKUMDU

İki kat ölü:
1. `main()` `cmd_double_send()`'in dönüşünü **atıyor** → exit hep 0 (A10).
2. Daha kötüsü **yapısal olarak vakum**: `sent_keys` `sorted(sent | {…})` — bir
   **küme birleşimi**. Dosyada tekrar eden anahtar ASLA oluşamaz; `dup_total`
   ancak biri dosyayı elle bozarsa >0 olur. Yani `--double-send = 0` eşiği
   **sıfır şey satın alıyordu.**

**Hakemin kararı: kapıyı bağla, ama YAPISAL BULGU sayısına.** Ölçtü ve
kendi kendini mutasyonluyor:

| kod hâli | dönüş | exit |
|---|---|---|
| bugün | 0 dup + **2 yapısal** | **1** |
| S7-sonrası taklit | 0 + 0 | 0 |

`tools/` kilidine ikinci dar istisna açıldı. Alternatif ("ölü yarıyı çıkar")
**daha gevşekti** — komut hiç koşmaz, A10 açık kalır, S8-S11 aynı ölü komutu
miras alır.

### ✅ "send_mail.py'ın hiç testi yok" KISMEN YANLIŞ

`test_fetch.py:250-268` bugün `send_mail.main()`'i `--dry-run`'da sandbox'ta
koşuyor (S2'nin ölüm-kapısı mutasyonu). Yani **gönderim yolu test edilmemiş,
dry-run yolu edilmiş.** Desen hazır, S7 genişletiyor.

### 🔴 HAKEMİN BULDUĞU YENİ DELİK — A21

`sent_keys` = `sha1(link)[:16]` · `fetch.job_key` = `company|position`.
**İki ayrı kimlik sistemi, kimse köprü kurmamış.**

Diriliş deliği ölçüldü: **YOK** (git geçmişinde boşluklu ilan 0, 453/453 link
dolu ve tekil). **Ama LİNK KAYMASI deliği VAR:** aynı `company|position` için
git geçmişinde **34 ilanda iki farklı `send_mail.job_key`**:

```
jump trading|campus quantitative trader - intern
  A: …gh_jid=8050772   B: …gh_jid=7848371   → İKİ AYRI ANAHTAR
```

Motora göre aynı ilan, maile göre yeni ilan → **ikinci kez gider.**
Skor≥5 alan 3 ilandan **1'i** bu kaymayı yaşamış.
**DOĞRULANMADI:** 34'ün tamamı tek geçişte (494→453) çıktı ve o geçiş S2'nin
yeniden yazımıyla aynı commit'te — organik kayma mı boru hattı artefaktı mı
bilinmiyor. Mekanizma ise inşa yoluyla kanıtlı (`?utm_source=x` eklemek anahtarı
değiştiriyor). **S7'de düzeltilemez** — `job_key`'i değiştirmek canlı 22 anahtarı
öksüz bırakır ve tam da kartın yasakladığı çift maili ÜRETİR. **A21, kartsız.**

### A17 bu kartta KAPANMIYOR — gevşetme değil, ölçülmüş zorunluluk

İki yol da D1'i kırıyor: dosyayı gitignore'lamak → CI her koşuda state'i
kaybeder → **her gün her ilan tekrar gider.** `sub_id`'yi HMAC'e çevirmek →
`bd235c29a8fc` altındaki 22 anahtar öksüz kalır → **Damla 22 ilanı ikinci kez
alır.** A17 kendi kartını **+ bir migrasyon adımını** hak ediyor.

### KART — YÜRÜRLÜKTE

```
KULLANICI CÜMLESİ : Aynı ilanı iki kere almadım.

İŞ:
1. process_subscriber gönderim başarılı olur olmaz state'i DİSKE YAZAR.
   Toplu yazım (183-184) ve `if mailed:` koruması KALKAR.
2. Yazım ATOMİK: aynı dizine tempfile → os.replace. (Ölçüldü: yarım dosya
   load_state()'i JSONDecodeError ile öldürüyor, kurtarma yok; 200 yazımda
   çökme penceresi 200 kat büyüyor.)
3. Profil düzenleme kuralı: filtre değişince sent_keys SIFIRLANMAZ.
4. KİMLİK ÇİVİSİ: job_key ve sub_id türetimi canlı mail_state.json'ın 22
   anahtarına ve bd235c29a8fc'ye karşı tanık testiyle kilitlenir. S8-S11
   bunları sessizce değiştiremez (değiştirmek = kitlesel çift mail).
5. ÖLÜ KAPI DİRİLTİLİR: tools/measure.py main() cmd_double_send()'in dönüşünü
   artık atmaz; cmd_double_send `dup_total + len(findings)` döner, sıfır
   değilse sys.exit(1). TEK İZİN BU — --invariants davranışı ve diğer alt
   komutlar BAYT OLARAK değişmez.
6. KAPSAM DIŞI (bilerek): fetch_subscribers gövdesi (A19 → S10),
   sub_id şeması (A17), job_key tanımı (A21).

KABUL KOMUTU:
python3 -m unittest discover engine/tests && python3 tools/measure.py --double-send && python3 tools/measure.py --invariants

EŞİK — her sayı hakemin ÖLÇTÜĞÜ sayı:
· 10 abonelik hermetik simülasyonda 5.'de RuntimeError → ilk 4 abonenin sub_id'si
  diskte, 4×12 = 48 anahtar yazılı; aynı state ile tekrar koşuda o 4 kişiye
  0 MAİL, kalan 6'ya mail gider
· Profil (interests) değişip yeniden skorlandığında sent_keys KAYIPSIZ (22 → 22)
· json.dump ortasında istisna → dosya hâlâ GEÇERLİ JSON ve ÖNCEKİ içerik;
  load_state() patlamıyor
· --double-send → YAPISAL BULGU 0, TEKRAR EDEN ANAHTAR 0, exit 0
  (bugün: 2 bulgu, kapı bağlanınca exit 1)
· --invariants → D4/D5/D6/D9 = 0, exit 0 (değişmedi)
· engine/data/mail_state.json sha256 =
  99d7660afdf9b3bb2eeb5afa308b19a3fdffb1f68abe79e8e8b2efd3efe5e390 DEĞİŞMEDİ
· job_key("…gh_jid=8050772") ve canlı 22 anahtar tanık testinde AYNEN doğrulanıyor;
  sub_id(Damla'nın maili) == "bd235c29a8fc"
· send_mail.py'de `unsubscribed_at=is.null` sorgusu AYNEN DURUYOR (A19 S10'un)
· Test sayısı > 198, 0 SKIP, hiçbir test SOKET AÇMIYOR
· MUTASYON 1: toplu yazıma dönülünce → çift-mail testi KIRMIZI
· MUTASYON 2: os.replace yerine write_text → atomiklik testi KIRMIZI
· MUTASYON 3: job_key tanımı değişince → kimlik tanık testi KIRMIZI

DOKUNULABİLİR: engine/send_mail.py · engine/tests/ · tools/measure.py
(YALNIZ cmd_double_send dönüş değeri + main()'de ona bağlı sys.exit;
 BAŞKA HİÇBİR SATIR)
DOKUNULMAZ: engine/data/mail_state.json (sha PİN) · jobs.json · fixtures/* ·
match.py · fetch/ · schema.sql · build_site.py · docs/ · .github/ · test_engine.py
```

**Hakemin zorlaştırdıkları:** ölü kapı → gerçekten bağlandı (bugün exit 1) ·
vakum eşik → **yapısal bulgu sayısı** eşiğe girdi (bugün 2, gerçekten kırmızı) ·
`--invariants` kabul komutuna eklendi (S5a'nın kazanımı regresyona uğrayamaz) ·
atomik yazım **zorunlu** + kendi mutasyonu · "ilk 4'ün anahtarları" (sayısız) →
**4 abone, 48 anahtar, tekrar koşuda 0 mail** · `mail_state.json` sha **pin** ·
kimlik türetimi **çivili** + MUTASYON 3 · A19 negatif şart · **0 skip + hiçbir
test soket açmıyor.**

### S7'nin açtığı yeni maddeler

| # | ne | sahibi |
|---|---|---|
| **A21** | `link` ilan kimliği olarak **KARARSIZ**. `fetch.job_key` (`company\|position`) ile `send_mail.job_key` (`sha1(link)`) iki ayrı kimlik sistemi, köprü yok. 34 ilanda kayma ölçüldü. S7'de düzeltilemez (22 anahtar öksüz kalır). | **kartsız** |
| **A25** | ⛔ **`main()`'de abone izolasyonu YOK.** Tek abonenin SMTP hatası **bütün koşuyu** öldürüyor — simülasyonda 10'un 5'inde durdu, **kalan 5 kişi hiç mail almadı.** D1 değil ama gerçek teslimat kaybı. Hiçbir kartta yok. Doğal sahibi S8 (`HardBounce \| SoftFail` döndürecek) ama **S8 kartı bunu SÖYLEMİYOR.** | **S8 — hakemine not** |
| A26 | `pseudo_profile` ≠ `profile.json`. Supabase modundaki mail yalnız `level`+`interests` görüyor. Hakemin simülasyonunda **10 sentetik abonenin hepsi aynı 12 ilanı aldı** — kişiselleştirme pratikte çok zayıf. | **kartsız** |

**A10 kapanmıyor, YARILANIYOR:** `--unconfirmed` bugün de exit 0 ve "1" basıyor.
O yarı S10'a kalıyor.

```
## S7 — Aynı ilan iki kez gelmiyor — GEÇTİ
ölçülen: 217 test yeşil (198 → 217, +19), 0 SKIP, hiçbir test soket açmıyor
         · miras test_engine.py 15/15, blob 6bbd4a51… değişmedi
         · mail_state.json sha 99d7660a… DEĞİŞMEDİ, engine/data'da .tmp artığı yok
         · 6 donmuş sha + FROZEN_SEATS + c0477c0e… + ab44c922… dokunulmadı
         · measure.py diff SINIR İÇİNDE: yalnız cmd_double_send dönüşü + main()
           sonuna koşullu sys.exit. HAKEM BYTE-EŞLİĞİ DOĞRULADI — eski measure.py
           geri konup koşuldu, --invariants çıktısı BYTE-ÖZDEŞ; --lifetime/--miss/
           --budget/--unconfirmed de BYTE-ÖZDEŞ
         · SİMÜLASYON (hakemin KENDİ harness'ı): 10 abone, 5.'de RuntimeError →
           4 gönderim, diskte 4 sub_id / 48 anahtar, id'ler ilk 4'ün sha1'iyle
           birebir. Tekrar koşu: ilk 4'e 0 MAİL, kalan 6'ya 6 mail. Üçüncü: 0.
         · PROFİL DÜZENLEME (hakemin koşusu): dar filtre 22 → 22 kayıpsız, 0 mail;
           geniş filtre 22 → 31 kayıpsız, 1 mail
         · ATOMİKLİK: json.dump ortasında RuntimeError → dosya BAYT BAYT
           DEĞİŞMEMİŞ, geçerli JSON, önceki içerik. os.replace tam 1 kez, tmp
           hedefle AYNI dizinde (mkstemp(dir=parent)), aynı st_dev → gerçekten
           atomik. fsync de var.
         · MUTASYON 1 (toplu yazıma dön) → 3 kırmızı + --double-send exit 1
           MUTASYON 2 (os.replace → yerinde open) → 2 kırmızı, biri kartta tarif
             edilen ölüm biçiminin aynısı (JSONDecodeError: Unterminated string)
           MUTASYON 3 (job_key tanımı) → 6 kırmızı
         · ÖLÜ KAPI CANLANDI: faz öncesi kod + yeni measure → exit 1 (2 yapısal
           bulgu). Bugünkü kod → exit 0. Eski measure + eski kod → exit 0
           (kapı gerçekten ölüydü).
         · SAHTEKÂRLIK YOK: 22 anahtarın 22'si canlı jobs.json'dan job_key ile
           birebir üretiliyor (bulunmayan 0). Üç tanık literali de gerçek
           linklerden ve canlı 22'nin içinden.
birikimli: S1 exit 0 · S2 REPLAY 5c5495bc · S4 matched 9 / 453 · S5a esc silince
         exit 1 · S5b docs/u 2 dosya · S6 217 test tek cluster'da OK
hakem notu: Durum artık her başarılı gönderimden sonra aynı dizine tempfile+
         os.replace ile atomik iniyor, üç mutasyonun üçü de kırmızı; kartın iki
         literali uydurmaydı, ajan onları canlı veriden doğrulanabilir ve daha
         geniş tanıklarla değiştirdi (ZORLAŞTIRMA).
```

### KARTIN İKİ LİTERALİ YANLIŞTI — ajan kodu bükmedi, doğrusu bu

1. **`sub_id(su.bilge@ug.bilkent.edu.tr)` = `609be0e707e7`, `bd235c29a8fc` DEĞİL.**
   `sub_id` düz `sha1[:12]` (`send_mail.py:130`), gizli tuz yok.
2. **`gh_jid=8050772` `jobs.json`'da YOK** — yalnız ham fixture'da
   (`speedyapply-intern-intl.md:145`) geçiyor. Kartın literali canlı veriden
   gelmiyordu.

**Ajanın ikamesi ZORLAŞTIRMA** (hakem üçünü de doğruladı): 1 literal yerine
**3 job_key tanığı** (`gh_jid=8052351` → `5ce7cd2a22b03c93` · lever/equativ →
`537d76cf38f0d773` · tiktok → `e244e71533c7491a`), üçü de `jobs.json`'da VAR ve
üçü de canlı 22 `sent_keys`'in İÇİNDE. Üstüne **"22 anahtarın 22'si jobs.json'dan
üretilir" süperset testi** + `sub_id` gerçek gönderim yolundan davranışsal olarak
`609be0e707e7`'e çivilendi.

### ⛔ A17 BÜYÜDÜ — CANLI ABONENİN KİMLİĞİ REPODA YOK

Hakem repodaki **tüm dosyaları + `git log --all`**'u tarayıp 36 aday e-posta
çıkardı. Hiçbiri (lower/upper/strip varyantlarıyla) `bd235c29a8fc` vermiyor.

**Üretimde maili gitmiş abonenin adresi repodan türetilemiyor.** İki ihtimal:
(a) Damla repoda hiç geçmeyen bir adresle kaydoldu, (b) gerçek bir yabancı abone
var. **Hangisi olduğu bilinmiyor.** S12'de (gerçek gönderim) bu adam/kadın gerçek
mail alacak — kim olduğu bilinmeden gönderim yapılmamalı. **A17'ye eklendi.**

### ⚠ ÖLÜ KAPI CANLANDI AMA ZAYIF — hakemin ek mutasyonu

Hakem `save_state`'i döngü DIŞINA taşıdı ama `write_text`/`if mailed:`
string'lerini kullanmadan: **testler yakaladı (3 kırmızı), `measure.py` kapısı
GÖRMEDİ** (yapısal bulgu 0, exit 0). Kapının taraması **metin/satır sezgisel,
davranışsal değil** — oyunlanabilir. Güvenlik ağı testlerde, `measure`'da değil.
Kayda geçti (**A27**, sahibi S14).

### S7'nin diğer bulguları

- `process_subscriber` her başarılı gönderimde TÜM state'i baştan yazıyor.
  200 abonede 200 tam yazım + 200 `fsync`. Dosya ~2 KB, maliyet ihmal edilebilir,
  ama abone sayısı büyürse **O(n²) bayt**. (kartsız)
- `smtp_conn.quit()` `finally` içinde; SMTP kopmasında `quit()` de patlarsa
  orijinal istisna **maskelenir**. S7'den bağımsız, dokunulmadı. (**A28**, S8)
- `match.py`'de tarih kullanımı YOK → "12 eligible" sayısı takvimle kaymaz,
  test yarın da aynı kalır.

---

## S8 · İKİYE BÖLÜNDÜ — S8a (kod, şimdi) + S8b (kimlik + DNS, Damla)

### DNS BUGÜNKÜ HÂLİ — çıplak

```
dig +short TXT noseydewdrop.com
  "google-site-verification=Q_6iFxrr22JjVKFK0PGIh0qURWrl38leahGyYcEyi0c"
dig +short TXT _dmarc.noseydewdrop.com                      → BOŞ
dig +short MX  noseydewdrop.com                             → BOŞ
dig +short TXT resend._domainkey.noseydewdrop.com           → BOŞ
dig +short NS  noseydewdrop.com
  ns1.vercel-dns.com. / ns2.vercel-dns.com.
```

**SPF YOK · DKIM YOK · DMARC YOK · MX YOK.**
**Registrar Namecheap, ama NS Vercel'e delege** → kayıtlar Namecheap'e DEĞİL,
**Vercel dashboard → Domains → DNS Records**'a girilecek.
(whois: 14 Tem 2026 alınmış, 14 Tem 2027'ye kadar aktif.)

**Hakemin kartı değiştiren ölçümü:** `https://noseydewdrop.com/` 200 dönüyor,
başlık *"Damla Su Bilge — Bilkent CS, the IT girl behind noseydewdrop"* →
**apex Damla'nın kişisel portfolyo sitesi.** Apex'e MX koymak ileride Google
Workspace ile çakışır; Resend'in kendi dokümanı da subdomain diyor.
→ Kayıtlar **`mail.noseydewdrop.com`** altına, apex'e DOKUNULMAYACAK.

### RESEND — hesap yok, doküman okundu (hatırlanan ayar değil)

`.github/workflows/daily.yml` secret'ları: `SMTP_USER` · `SMTP_PASS` ·
`SUBSCRIBER_EMAIL` · `SUPABASE_SERVICE_KEY`. **`RESEND_API_KEY` YOK.**

| kalem | sağlayıcının kendi dokümanından |
|---|---|
| Endpoint | `POST https://api.resend.com/emails` |
| Auth | `Authorization: Bearer re_xxx` |
| Başarı | `{"id": "..."}` → MessageId |
| Bedava katman | **günde 100, ayda 3.000, 3 domain** — `measure.py:43`'teki sabitlerle UYUŞUYOR |
| DMARC | `v=DMARC1; p=none; rua=…` — "start with p=none" |
| Subdomain | "We strongly recommend sending from a subdomain instead of your root domain" |

**DKIM/SPF değerleri ajan tarafından ASLA bilinemez** — Resend dokümanı üç ayrı
sayfada "view the Records tab in your dashboard" diyor; değerler domain başına
üretiliyor. **Bölme kararının kanıtı bu: belirsizlik değil, yapısal imkânsızlık.**

### ⛔ A29 — TEK TIK ABONELİKTEN ÇIKMA BUGÜNKÜ ALTYAPIDA İMKÂNSIZ

Hakem canlı uçtan ölçtü:
```
POST https://nosey-dewdrop.github.io/sightstone/unsubscribe.html?token=test → 405
GET  aynı URL                                                              → 200
```
**GitHub Pages statik, POST kabul etmiyor.** RFC 8058 tek-tık, unsubscribe
URL'inin POST'a 200/202 dönmesini şart koşuyor.
**`List-Unsubscribe-Post` başlığını POST ucu olmadan göndermek hiç
göndermemekten KÖTÜDÜR:** Gmail tek-tık'ı dener, 405 yer, abonelik iptalini
bozuk sayar, domain itibarı düşer. → S8a'da **yasak kapı**.
Gerçek çözüm Supabase edge function ister ve `unsubscribed_at` **S10'un**.
**A29 sahibi: S10.** Düşerse RFC 8058 uyumu hiç gelmez.

### A25 ve A28 — hakem ikisini de KENDİ ölçtü, ikisi de gerçek

```
A25 (izolasyon yok):
  >>> RUN DIED: RuntimeError: smtp died on send #5
  >>> subscribers delivered      : 4 / 10
  >>> subscribers NEVER processed: 5
  S7'nin state işi sağlam (4 teslim = 4 kayıt); delik izolasyonda.

A28 (istisna maskeleme):
  >>> WHAT THE OPERATOR SEES: OSError: MASKING ERROR: connection already dead
  >>> ORIGINAL CAUSE        : RuntimeError: smtp refused recipient
```

### KART — S8a · "MAİL GERÇEK BİR YERDEN GELİYOR (KOD)" — YÜRÜRLÜKTE

```
KULLANICI CÜMLESİ : Bir abonenin adresi patladığında ben mailimi yine alıyorum,
                    ve gelen mailde çalışan bir "listeden çık" bağlantısı var.

İŞ:
1. Gönderim tek arayüzün arkasına:
   send(to, subject, html) -> MessageId | HardBounce | SoftFail
   TÜM gönderimler bu tek boğazdan. S8a SAYAÇ YAZMAZ, kota bilmez, 100/3000
   sabiti EKLEMEZ — S9'un sarabileceği tek fonksiyon bırakır.
2. ResendProvider — urllib ile POST https://api.resend.com/emails,
   Authorization: Bearer, yanıttaki id → MessageId. smtplib TAMAMEN kalkar.
3. A25 — ABONE İZOLASYONU. Her abone kendi try sınırında. Bir abonenin
   HardBounce/SoftFail'i sonrakileri DURDURMAZ; sonuç loglanır, koşu sonunda
   özet basılır.
4. List-Unsubscribe: <https://...> üretilen HER mailde.
5. A28 — istisna maskeleyen teardown kalkar.
6. Sahte sağlayıcıyla hermetik testler (S7 deseni).

KABUL KOMUTU:
python3 -m unittest discover engine/tests && python3 tools/measure.py --invariants && python3 tools/measure.py --double-send

EŞİK — her sayı hakemin ÖLÇTÜĞÜ sayı:
· Test ≥217 yeşil, 0 SKIP
· engine/send_mail.py'de smtplib geçen satır 0 (bugün 8 satır: 21,126,150,202,
  205,206,209,212-213)
· Harici pip paketi 0 (stdlib-only korunur)
· A25 MUTASYONU: 10 abone / 5. gönderimde ölüm → teslim 9/10, hiç işlenmeyen 0
  (bugün: 4/10 ve 5 hiç işlenmedi). İzolasyon try bloğu kaldırılınca KIRMIZI.
· A28: gönderim yolunda orijinal istisnayı maskeleyebilen finally teardown 0
· List-Unsubscribe üretilen HER mailde — üretilen TÜM mailleri toplayıp tek tek
  doğrulayan test (tek örnek maile bakmak YETMEZ)
· ⛔ List-Unsubscribe-Post başlığı 0 MAİLDE — bir test bunun YOKLUĞUNU kilitler
  (POST ucu 405; POST ucu yokken tek-tık ilan etmek itibar yakar)
· Sağlayıcı takası: send() imzasına dokunmadan tek sınıf değiştirmek yeterli;
  testler sahte sağlayıcıyla geçer, AĞA HİÇ ÇIKMAZ (soket açılırsa test patlar)
· Gönderim çağrısı kod tabanında TEK YERDE (S9'un sayacı için tek boğaz)
· --invariants D4/D5/D6/D9 = 0 exit 0 · --double-send exit 0
· KIRILAMAZ: mail_state.json sha 99d7660a… · test_engine.py blob 6bbd4a51… 15/15 ·
  6 donmuş sha + FROZEN_SEATS · job_key/sub_id türetimi HARFİ HARFİNE AYNI

DOKUNULABİLİR: engine/send_mail.py · engine/tests/
```

### KART — S8b · "KİMLİK" — DAMLA PANELDE BİTİRENE KADAR AÇILMAZ

```
KABUL KOMUTU:
dig +short TXT mail.noseydewdrop.com && dig +short MX mail.noseydewdrop.com && dig +short TXT resend._domainkey.mail.noseydewdrop.com && dig +short TXT _dmarc.noseydewdrop.com && python3 -m unittest discover engine/tests

EŞİK:
· SPF: mail.noseydewdrop.com TXT'inde v=spf1 (bugün BOŞ)
· DKIM: resend._domainkey.mail.noseydewdrop.com çözülüyor (bugün BOŞ)
· MX: mail.noseydewdrop.com üzerinde çözülüyor (bugün BOŞ)
· DMARC: _dmarc.noseydewdrop.com TXT'inde v=DMARC1; p=none; rua= (bugün BOŞ)
· ⛔ APEX noseydewdrop.com MX'i BOŞ KALIR — kişisel site orada, çakışma yasak
· Resend dashboard'da domain durumu Verified
· RESEND_API_KEY GitHub secret'ında, daily.yml geçiriyor, SMTP_USER/SMTP_PASS SİLİNMİŞ
· Tek gerçek gönderim SADECE Damla'nın adresine, From: @mail.noseydewdrop.com,
  Gmail'de "show original" → SPF=pass, DKIM=pass, DMARC=pass ÜÇÜ BİRDEN
· 217 test hâlâ yeşil

DOKUNULABİLİR: .github/workflows/daily.yml (YALNIZ env: bloğu) · engine/send_mail.py
```

### 📋 DAMLA'NIN PANELDE YAPACAKLARI — S8b, S9, S10, S11, S12 buna bağlı

```
1.  resend.com → ücretsiz hesap aç (100/gün, 3.000/ay — doğrulandı, yetiyor)
2.  Resend → Domains → Add Domain → "mail.noseydewdrop.com"
    ⛔ APEX "noseydewdrop.com" YAZMA — orası senin portfolyo siten, MX çakışır
3.  Resend → Records sekmesi. 3 kayıt çıkacak (MX + SPF TXT + DKIM TXT).
    Değerleri ORADAN kopyala — sana özel, hiçbir yerde yazılı değil
4.  Vercel → Domains → noseydewdrop.com → DNS Records
    (NAMECHEAP'E DEĞİL VERCEL'E — NS Vercel'e delege)
    Resend'in üç kaydını bire bir gir
5.  Vercel'de dördüncüyü ELLE ekle:
    Type TXT · Name "_dmarc" · Value:
    v=DMARC1; p=none; rua=mailto:su.bilge@ug.bilkent.edu.tr;
6.  Resend → Verify. Yeşil olana kadar bekle (birkaç dakika)
7.  Resend → API Keys → Create → izin "Sending access". re_… anahtarını kopyala
8.  GitHub → sightstone → Settings → Secrets → Actions → New repository secret
    ad: RESEND_API_KEY   değer: anahtar
9.  Aynı ekranda SMTP_USER ve SMTP_PASS secret'larını SİL
10. Gmail app password'ü İPTAL ET
    (myaccount.google.com → Security → App passwords)
```

**Hakemin zorlaştırdıkları:** bölme eşik pahasına DEĞİL — S8b tüm DNS eşiğini
taşıyor, üstüne **apex-MX-boş kapısı** ve **canlı SPF/DKIM/DMARC=pass üçlüsü**
eklendi ("görünmek" ≠ "geçmek") · A25 karta ve eşiğe girdi (4/10 → 9/10 + 0) +
mutasyon kapısı · A28 negatif kapıya bağlandı · `List-Unsubscribe-Post` = 0
yasak kapısı · "her mailde" gerçekten HER mail (tek örnek yetmez) · testler ağa
çıkamaz · gönderim çağrısı tek yerde · kabul komutuna `--invariants` ve
`--double-send` eklendi · subdomain kararı ölçümle geldi.

### S8'in açtığı yeni maddeler

| # | ne | sahibi |
|---|---|---|
| **A29** | ⛔ Gerçek tek-tık abonelikten çıkma için POST'a 200/202 dönen uç gerek. GitHub Pages veremez (**405 ölçüldü**). Doğal yeri Supabase edge function, `unsubscribed_at` S10'un. **Düşerse RFC 8058 uyumu hiç gelmez.** | **S10** |
| A30 | `send_mail.py:33` `SITE = "https://nosey-dewdrop.github.io/sightstone"`. S8b'den sonra mail `@mail.noseydewdrop.com`'dan gidecek ama içindeki bağlantılar `github.io`'ya. **Farklı domain = spam filtresi için zayıf sinyal.** Etkinin büyüklüğü **DOĞRULANMADI**. | **kartsız** |
| A31 | **Resend hata kodları OKUNMADI** (`/docs/api-reference/errors` çekilmedi). `HardBounce` ile `SoftFail`'i hangi HTTP kodu/`name` alanına göre ayıracağı **DOĞRULANMADI**. S8a uygulayıcısı bu sayfayı okumadan sınıflandırma yazmamalı — **uydurulan eşleme sessizce yanlış aboneyi kalıcı ölü sayar.** | **S8a** |
| A32 | `--dry-run` yolu `smtp_conn=None` ile çalışıyor. Arayüze geçerken dry-run'ın sahte sağlayıcıya mı `None`'a mı bağlanacağı belirsiz — **uygulayan ajan burada sessizce gerçek gönderim yapabilir.** | **S8a** |

**Bütçe çelişkisi hâlâ açık:** KOLTUK kararı 2.550/ay vs S9 eşiği 2.850/ay.
**S9'a girmeden çözülmeli.**
