# ADR-001: Satış Fiyatı Düzeltmede Etkin İndirim Modeli (r, c)

|            |                                                      |
| ---------- | ---------------------------------------------------- |
| **Durum**  | Kabul edildi (Accepted)                              |
| **Tarih**  | 06.11.2026                                           |
| **Bağlam** | Dynamics POS fiyat düzeltme aracı (Excel / uygulama) |

---

## 1. Bağlam ve Problem

Hedef, müşteriye yapılan **son satış fiyatını** (net) tutturmaktır. Örneğin hedef 155.000 TL ise POS'a girilecek ürün fiyatları buna göre ayarlanır.

Mevcut yöntem şu formüle dayanır:

```
POS fiyatı = Son fiyat + İndirim        (=F2 + N(I2))
```

Bu formül **indirimin sabit tutar olduğunu** varsayar. Ancak düğün kampanyası üründe **%10 yüzdelik** indirim verir. POS fiyatını değiştirince sistem indirimi yeniden hesaplar ve net fiyat hedeften sapar.

Ek olarak:

- AFC gibi kampanyalar **ekstra indirim** getirebilir. Bu yüzden %10 tek başına yeterli olmaz.
- Sepette düğün, sabit indirimli (oliz) ve indirimsiz (ankastre) ürünler karışıktır.
- Mevcut uygulama farkı **tüm ürünlere eşit böler**. Bu, düğün dışı ürünlerde istenmeyen fiyat değişimi yaratır.
- Fiyat değişince eşikli kampanyalar devreye girip çıkabilir.

## 2. Örnekler

### 2.1 Tek ürün, yalnızca düğün %10 (ürün 10121)

| Adım           | Değer     |
| -------------- | --------- |
| İndirim öncesi | 38.299,00 |
| İndirim (%10)  | 3.829,90  |
| Hedef net      | 30.000,00 |

**Mevcut formül:**

```
30.000 + 3.829,90 = 33.829,90
Sistem: 33.829,90 × %10 = 3.382,99 indirim
Net = 30.446,91 ✗ (hedef 30.000)
```

**Yeni formül:**

```
p = 30.000 / 0,9 = 33.333,33
Sistem: 33.333,33 × %10 = 3.333,33 indirim
Net = 30.000,00 ✔
```

### 2.2 Tek ürün, düğün %10 + AFC ekstra %2 (ardışık)

```
Etkin oran: r = 1 − (0,9 × 0,98) = 0,118
Hedef net 80.000 → p = 80.000 / 0,882 = 90.702,95
Kontrol: 90.702,95 × 0,882 ≈ 80.000,00 ✔
```

### 2.3 Çok ürünlü sepet

6 kalem girilir. İlk 3'ü düğün ürünü (düzenlenebilir), diğerleri ankastre (düzenlenemez). Fark **yalnızca ilk 3 ürüne** dağıtılır, ankastre ürünlere dokunulmaz.

## 3. Karar

### 3.1 Her satır için iki parametre tutulur

Satırın indirimi, POS fiyatı `p` cinsinden doğrusal modellenir:

```
d = r·p + c
net = p − d = p·(1 − r) − c
```

Buradan hedef net `N` için girilecek fiyat:

```
p = (N + c) / (1 − r)
```

| Kalem tipi              | r          | c           |
| ----------------------- | ---------- | ----------- |
| Düğün (%10)             | 0,10       | 0           |
| Düğün + yüzdelik ekstra | etkin oran | 0           |
| Oliz / sabit indirim    | 0          | sabit tutar |
| Karışık                 | dolu       | dolu        |
| İndirimsiz              | 0          | 0           |

Ayrı bir "ekstra indirim" alanı eklenmez. Sistemin satıra uyguladığı **toplam etkin indirim** ölçülür.

### 3.2 r ve c otomatik kalibre edilir

Kullanıcı bu değerleri girmez. Uygulama her ürün için fiyatı iki farklı değerde (p₁, p₂) sorgular ve sistemin verdiği indirimleri (d₁, d₂) okur:

```
r = (d₂ − d₁) / (p₂ − p₁)
c = d₁ − r·p₁
```

- İndirim fiyatla orantılı değişiyorsa → r > 0, c = 0
- İndirim sabit kalıyorsa → r = 0, c > 0
- İkisi de varsa → ikisi de dolu

### 3.3 Fark yalnızca düzenlenebilir kalemlere, net uzayında dağıtılır

Brüt fiyat üzerinden değil, **net üzerinden orantılı** dağıtılır:

```
F      = Σ net_i                (tüm sepet)
ΔF     = Hedef − F
A      = düzenlenebilir kalemler
k      = (Σ_A net_i + ΔF) / Σ_A net_i
net_i' = net_i · k               (i ∈ A)
p_i'   = (net_i' + c_i) / (1 − r_i)
```

Düzenlenemez kalemler (ankastre vb.) olduğu gibi kalır.

### 3.4 Doğrulama turu zorunludur

Hesaplanan fiyatlar yazıldıktan sonra:

1. Sistemin gerçek sepet toplamı okunur.
2. `fark = hedef − gerçek_toplam` hesaplanır.
3. Fark, son düzenlenebilir kalemde `fark / (1 − r)` kadar düzeltilir (r = 0 ise doğrudan `fark`).
4. Fark 0,00 olana kadar en fazla 2-3 tur tekrarlanır.

## 4. Referans Uygulama

```python
from decimal import Decimal as D, ROUND_HALF_UP

def q(x): return x.quantize(D("0.01"), rounding=ROUND_HALF_UP)

def calibrate(price_fn, p1, p2):
    """price_fn(p) -> sistemin o fiyatta verdiği indirim"""
    d1, d2 = price_fn(p1), price_fn(p2)
    r = (d2 - d1) / (p2 - p1)
    c = d1 - r * p1
    return r, c

def solve(items, target):
    """
    items: [{"id", "p", "r", "c", "editable": bool}]
    """
    for it in items:
        it["net"] = it["p"] * (1 - it["r"]) - it["c"]

    F  = sum(it["net"] for it in items)
    A  = [it for it in items if it["editable"]]
    nA = sum(it["net"] for it in A)
    if nA + (target - F) <= 0:
        raise ValueError("Düzenlenebilir kalemler hedefe yetmiyor")

    k = (nA + (target - F)) / nA
    return {
        it["id"]: q((it["net"] * k + it["c"]) / (1 - it["r"]))
        for it in A
    }
```

## 5. Değerlendirilen Alternatifler

| Alternatif                              | Neden reddedildi                                                        |
| --------------------------------------- | ----------------------------------------------------------------------- |
| Mevcut `F + İndirim` formülü            | Yüzdelik indirimde yanlış sonuç verir (örnek 2.1).                      |
| Düğün oranını %10 sabit kodlamak        | AFC gibi ekstra kampanyalarda bozulur.                                  |
| Ayrı "ekstra indirim" alanı eklemek     | Kullanıcıya yük bindirir, kampanya her değiştiğinde güncelleme gerekir. |
| İteratif deneme-yanılma (Excel döngüsü) | Yakınsar ama yavaş ve kontrolsüzdür. Kapalı form çözüm mevcut.          |
| Farkı tüm kalemlere eşit bölmek         | Düğün dışı ürünlerin fiyatını (55 bin → 85 bin) bozar.                  |

## 6. Sonuçlar

**Olumlu**

- Düğün, oliz ve karışık kampanyalar tek formülle çözülür.
- Yeni kampanyalar kod değişikliği gerektirmez, kalibrasyon yakalar.
- Düğün dışı ürünler korunur.

**Olumsuz / Riskler**

- Kalibrasyon için ürün başına en az 2 ek sorgu gerekir (performans maliyeti).
- **Eşikli kampanyalar** ("X TL üstü ekstra %5") doğrusal modeli bozar. Fiyat eşiğin altına düşerse r değişir. Doğrulama turu bunu yakalar, ancak eşik civarında yakınsama olmayabilir. Bu durumda uyarı verilmelidir.
- Kuruş yuvarlaması ve KDV satır yuvarlaması 1-2 kuruş sapma yaratabilir. Doğrulama turuyla kapatılır.
- Karışık indirimde `d` fiyata göre gerçekten doğrusal değilse (ör. kademeli) iki nokta yetmez. Gerekirse 3 nokta ile doğrusallık kontrolü eklenir.

## 7. Uygulama Adımları

Yerel POS/web kalibrasyon bağlayıcısı henüz bulunmadığı için uygulama,
profil olmayan satırlarda dağıtımı engellemez. Bu durumda mevcut fiyat
ağırlıklı dağıtım kullanılır ve kullanıcıya POS doğrulaması gerektiği açıkça
bildirilir. Ancak kalibrasyonsuz satırlarda en az iki satır aynı indirim oranını
paylaşıyorsa bu satırlar yüzde kampanyası olarak tanınır:

- Yalnızca yüzde satırları varsa hedef net tutar, yüzde tamamlayıcısı ile
  brüt POS fiyatına çevrilir ve satırlara liste fiyatları oranında dağıtılır.
- Yüzde ve sabit satırlar birlikteyse yüzde satırlarının POS fiyatları
  korunur. Hedef net tutar ile yüzde satırlarının mevcut net toplamı
  arasındaki tutar, sabit indirim toplamı korunarak sabit satırlara liste
  fiyatları oranında katsayıyla dağıtılır.
- Tanıma uymayan veya hediye içeren satırlarda güvenli fiyat-ağırlıklı
  geri dönüş korunur; sonuç POS'ta doğrulanmalıdır.

"POS'ta görünen indirimli toplam" alanı doldurulduğunda ve satırların web
fiyatları bu toplamla uyuşmadığında, katalogdaki web fiyatı yerine POS'un
gösterdiği net sepet esas alınır. Kampanya oranı, katalog indirim oranı bu
oranın altında kalan satırların ortak yüzde grubu olduğu varsayımıyla

```
POS'ta görünen toplam
  = Σ yüzde grubu net + Σ sabit satır web fiyatı
  = Σ yüzde grubu ilk fiyat × (1 − oran) + Σ sabit satır web fiyatı
```

denkleminden tek olarak çözülür. Yüzde grubundaki satırların POS fiyatları
liste fiyatında korunur; sabit satırların POS fiyatları, hedef net ile toplam
indirim korunacak şekilde liste fiyatları oranında dağıtılır. Bu kural,
katalogdaki normal online indirimin POS kampanya oranından farklı olduğu
durumları kapsar; sonuç yine POS'ta doğrulanmalıdır.

Kalibrasyon profili sağlandığında aşağıdaki ADR çözümü kullanılır.

1. Satır modeline ölçülmüş kampanya profili (`r`, `c`, `editable`) ekle.
2. Kalibrasyon fonksiyonunu yaz ve ürün başına önbellekle (kampanya değişirse geçersiz kıl).
3. Dağıtımı "tüm ürünlere eşit" yerine "seçili ürünlere net üzerinden orantılı" yap.
4. Doğrulama/düzeltme turunu ekle (maks. 3 tur, sonuçta fark ≠ 0 ise uyarı ver).
5. Gerçek vakalarla regresyon testi yaz: ürün 10121, AFC sepeti (155.000 hedefi), karışık sepet.

## Yukarıdaki çözüm doğru değil, aşağıda genel bir çözüm bulundu:

yüzdeli ürün indirimi çözüm

OCD K 752 EWS: 33.999 → indirimli fiyat: 30.599,1

ADE 9062 S1: 32.499 → indirimli fiyat: 29.249,1

AFC 341 S: 34.499 → indirimli fiyat: 31.049,1

not: yukarıdakilerin hepsine %10 uygulanıyor

Indirim Öncesi Tutar: 100997
Indirimli Sepet Tutarı: 90897.3
Toplam Indirim: 10099.7

son pos fiyatı: 81.000 tl

indirimli sepet %10 üzerinden bulunmuş 100997 × 0,9 = 90897,3

ben indirimli sepeti 81.000 yapmam lazım

y * 0,9 = 81.000 TL

Y = 90.000 TL

Y= pos uygulamasında gireceğim değer, bunu girince indirimli sepet 81.000 tl oluyor.

eğer hem düğün hem olizli olursa

OCD K 752 EWS: 33.999 → indirimli fiyat: 30.599,1

ADE 9062 S1: 32.499 → indirimli fiyat: 29.249,1

AFC 341 S: 34.499 → indirimli fiyat: 31.049,1

901 KMP I: 56.299,00 → indirimli fiyat: 46299 → 10.000,00 TL Sabit İndirim

Indirim Öncesi Tutar: 157296
Indirimli Sepet Tutarı: 137196.3
Toplam Indirim: 20099.7

son fiyat(indirimli sepet tutarı olarak ayarlansın): 123.000 TL

değişimi sadece sabit olan üründe yaptım:

901 KMP I → 42.102,70 TL olarak değiştirildi.

(Not: 901 KMP I için yeni liste fiyatı hesaplaması: 143.099,70 - 100.997,00 = 42.102,70)

{Yeni Liste Fiyatı (901 KMP I)} = S - 80.897,30

alternatif sadece sabit üründe çıkınca

Indirim Öncesi Tutar: 143099.7
Indirimli Sepet Tutarı: 123000.00000000001
Toplam Indirim: 20099.7

901 kmp ı: 56299 → 42.102,70 olarak değiştirince tam oldu.

excel de şöyle çalıştı (ama tek üründe)

Teşekkür ederim! Algoritmanın oturmasına çok sevindim.

Mantığı tam olarak istediğiniz gibi Excel formülüne dökelim.

Excel tablonuzu şu sütun yapısına göre kurabilirsiniz:

### Tablo Yapısı

| Hücre  | Başlık                                | Açıklama / Gireceğiniz Değer                                                   |
| ------ | ------------------------------------- | ------------------------------------------------------------------------------ |
| **A2** | **Orijinal Yüzdeli Ürünler Toplamı**  | Yüzde 10 indirim alan 3 ürünün orijinal liste fiyatı toplamı _(Örn: `100997`)_ |
| **B2** | **Sabit İndirim Tutarı**              | Sabit indirimli üründen düşen indirim tutarı _(Örn: `10000`)_                  |
| **C2** | **Sabit Ürünün Orijinal Fiyatı**      | Sabit indirim uygulanan ürünün orijinal liste fiyatı _(Örn: `56299`)_          |
| **D2** | **Hedef Son Fiyat (Sepet Tutarı)**    | Kasada ulaşmak istediğiniz indirimli tutar _(Örn: `123000`)_                   |
| **E2** | **POS'a Girilecek Sabit Ürün Fiyatı** | **FORMÜLLÜ HÜCRE (Sonuç)**                                                     |

---

### Excel Formülü

```excel
=D2 - (A2 * 0.9) + B2

```

---

### Nasıl Çalışır? (Örnek Sağlama)

Formüldeki değerleri ikinci senaryonuz üzerinden kontrol edelim:

- **A2:** `100997` _(33.999 + 32.499 + 34.499)_
- **B2:** `10000`
- **C2:** `56299` _(Formülde kullanılmasına gerek kalmıyor, doğrudan farkı hesaplıyor)_
- **D2:** `123000` _(Hedeflenen Son Fiyat)_

Formülün hesabı:
`123000 - (100997 * 0.9) + 10000`
`123000 - 90897.3 + 10000` = **`42.102,70 TL`**

**Sonuç:** Excel size direkt olarak **901 KMP I** ürününün POS'a girilmesi gereken fiyatını (**42.102,70 TL**) verecektir.

Yüzdeli ürünleri orijinal fiyatıyla girip, sabit ürünü E2'de çıkan sonuçla girdiğinizde sepet tam olarak D2 hücresine yazdığınız hedef tutara eşitlenir.

doğrulanmayan birden fazla için formül (pos'ta dene)

901 KMP IG(SECİLİ KURUTMA VE ANKASTREDE 17.850 TL):

ürün indirimsiz fiyatı: 57.599,00 TL

normal indirimli fiyatı: 47.599 TL (iki kampanya birbirini karşılamaz, o yüzden diğer yüksek fiyatlı 17.850 tl pos'a giriyor)

bu ürünün kendi indirimi değil ama toplama indirim eklenmiş oluyor.

Indirim Öncesi Tutar: 214895
Indirimli Sepet Tutarı: 187045
Toplam Indirim: 27850

not: bu örnekte yüzdeli indirim az olduğu için, en yüksek indirimleri pos görüyor, görüldüğü gibi 10.000 + 17850 = 27850 aktif ve düğünler aktif değil çünkü onların indirimleri bu kampanyaya göre daha az.

son fiyat: 165.000 TL

fiyatlar sadece bu ürünlerde değiştirilince:

901 KMP I: 43.000,00

901 KMP IG: 48.853,00

Indirim Öncesi Tutar: 192850
Indirimli Sepet Tutarı: 165000
Toplam Indirim: 27850

yukarıdaki gibi tam bulunabiliyor çünkü toplam indirim sabit, yüzde indirimi deaktif.

eğer yüzdeli indirimle birlikte sabit indirim birlikte aktif olursa:

farklı ürün eklendi, fiyat oranlı oldu(tv 8.000 tl + kurutma 10.000 tl) = 18.000tl sabit

ürün satırı silindi: 901 KMP I

901 KMP IG + A 965 C AI

A 965 C AI:

normal fiyatı: 71.399,00

oliz: 63.399 TL

yüzdeli olanlar toplamı: 3399.9 + 3249.9 +3449.9 = 10.099,7

Indirim Öncesi Tutar: 229995
Indirimli Sepet Tutarı: 201895.3
Toplam Indirim: 28099.7

son fiyat: 175.000 TL

Indirim Öncesi Tutar: 203099.7
Indirimli Sepet Tutarı: 175000
Toplam Indirim: 28099.7

Bu senaryoda sistem karma (hibrit) indirim mantığıyla çalışıyor: Yüzdeli ürünlerin indirimi ($10.099,70\text{ TL}$) sepetteki fiyatlarına bağlı olarak değişirken, sabit ürünlerin indirimleri ($18.000\text{ TL}$) fiyat ne olursa olsun sabit kalıyor.

Mevcut Durum Analizi

Yüzdeli Ürünler Orijinal Fiyat Toplamı ($A$): $100.997,00\text{ TL}$ (Sağladığı %10 İndirim: $10.099,70\text{ TL}$)

Sabit İndirimli Ürünlerin Toplam İndirimi ($B$): $18.000,00\text{ TL}$ ($8.000 + 10.000$)

Mevcut Toplam İndirim Tutarı: $10.099,70 + 18.000,00 = \mathbf{28.099,70\text{ TL}}$

Mevcut İndirim Öncesi Tutar: $229.995,00\text{ TL}$

Mevcut İndirimli Sepet Tutarı: $201.895,30\text{ TL}$

Genel Matematiksel Formül

Hedeflediğiniz herhangi bir İndirimli Sepet Tutarı ($S$) için POS'a girilmesi gereken Yeni Toplam Liste Fiyatı ($X$):

Yüzdeli ürünlerin fiyatları sabit tutulduğunda (%10 indirimleri $10.099,70\text{ TL}$ olarak kalacağı için):

$$X = S + \text{Sabit İndirimler} + \text{Yüzdeli Ürünlerin Sağladığı İndirim}$$

$$X = S + 18.000 + 10.099,70 = \mathbf{S + 28.099,70\text{ TL}}$$

Fiyat Değişikliği Uygulaması

Sabit indirimli ürünlerin (901 KMP IG ve A 965 C AI) toplam liste fiyatını ayarlamak için yapmanız gerekenler:

1. Sabit Ürünlerin POS Fiyatları Toplamını Bulma

$$\text{Sabit Ürünler POS Toplamı} = X - \text{Yüzdeli Ürünler Toplamı}$$

$$\text{Sabit Ürünler POS Toplamı} = (S + 28.099,70) - 100.997 = \mathbf{S - 72.897,30\text{ TL}}$$

2. Sabit Ürünlere Orantılı Dağıtma Katsayısı

Sabit indirimli iki ürünün orijinal liste fiyatları toplamı:

$$57.599 + 71.399 = \mathbf{128.998,00\text{ TL}}$$

$$\text{Katsayı} = \frac{\text{Yeni Sabit Ürünler POS Toplamı}}{128.998}$$

Örnek Hesaplama (Hedef Sepet $S = 175.000\text{ TL}$ olsun)

Gerekli Toplam Liste Fiyatı ($X$):

$$175.000 + 28.099,70 = \mathbf{203.099,70\text{ TL}}$$

Sabit Ürünler POS Toplamı:

$$203.099,70 - 100.997,00 = \mathbf{102.102,70\text{ TL}}$$

Orantılı Dağıtım Katsayısı:

$$\text{Katsayı} = \frac{102.102,70}{128.998} \approx \mathbf{0,791506}$$

Sabit Ürünlerin POS'a Girilecek Fiyatları:

901 KMP IG: $57.599 \times 0,791506 = \mathbf{45.590,04\text{ TL}}$

A 965 C AI: $71.399 \times 0,791506 = \mathbf{56.512,66\text{ TL}}$

Excel Formülü

Excel'de hedef sepet tutarını yazdığınızda sabit ürünlere girilecek POS fiyatlarını otomatik çıkarmak için:

Hücre

Açıklama

Değer / Formül

A2

Yüzdeli Ürünler Orijinal Toplamı

100997

B2

Toplam Sabit İndirim Tutarı

18000

C2

Sabit Ürünler Orijinal Liste Toplamı

128998

D2

Hedef Sepet Tutarı (Gireceğiniz Tutar)

(Örn: 175000)

E2

Gerekli Toplam Liste Fiyatı

=D2 + B2 + (A2 * 0.1)

F2

Sabit Ürünler İçin Dağıtım Katsayısı

=(E2 - A2) / C2

Sonuç: Her sabit ürünün orijinal liste fiyatını F2 hücresi ile çarptığınızda, POS'a girilecek yeni fiyatları elde edersiniz ve sepet tam olarak hedeflediğiniz D2 tutarına ulaşır.

### son değişiklikten sonra basit bir sorun kaldı:

şimdi şu an sorun bir nevi çözüldü; örneğin 81 bin örneğinde artık 90.000 doğru görünüyor ama ikinci olizli ürün örneğimiz 901 kmpı ekleyince değer olarak 141.019,90 tl bulunuyor, eğer herhangi bir üründe hediye dahil checkbox seçersem pos giriş tutarı 143.099,70 tl oluyor....
