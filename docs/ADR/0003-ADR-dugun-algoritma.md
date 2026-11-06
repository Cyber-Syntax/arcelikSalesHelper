# ADR-001: Satış Fiyatı Düzeltmede Etkin İndirim Modeli (r, c)

| | |
| --- | --- |
| **Durum** | Kabul edildi (Accepted) |
| **Tarih** | 06.11.2026 |
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

| Adım | Değer |
| --- | --- |
| İndirim öncesi | 38.299,00 |
| İndirim (%10) | 3.829,90 |
| Hedef net | 30.000,00 |

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

| Kalem tipi | r | c |
| --- | --- | --- |
| Düğün (%10) | 0,10 | 0 |
| Düğün + yüzdelik ekstra | etkin oran | 0 |
| Oliz / sabit indirim | 0 | sabit tutar |
| Karışık | dolu | dolu |
| İndirimsiz | 0 | 0 |

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

| Alternatif | Neden reddedildi |
| --- | --- |
| Mevcut `F + İndirim` formülü | Yüzdelik indirimde yanlış sonuç verir (örnek 2.1). |
| Düğün oranını %10 sabit kodlamak | AFC gibi ekstra kampanyalarda bozulur. |
| Ayrı "ekstra indirim" alanı eklemek | Kullanıcıya yük bindirir, kampanya her değiştiğinde güncelleme gerekir. |
| İteratif deneme-yanılma (Excel döngüsü) | Yakınsar ama yavaş ve kontrolsüzdür. Kapalı form çözüm mevcut. |
| Farkı tüm kalemlere eşit bölmek | Düğün dışı ürünlerin fiyatını (55 bin → 85 bin) bozar. |

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

1. Satır modeline ölçülmüş kampanya profili (`r`, `c`, `editable`) ekle.
2. Kalibrasyon fonksiyonunu yaz ve ürün başına önbellekle (kampanya değişirse geçersiz kıl).
3. Dağıtımı "tüm ürünlere eşit" yerine "seçili ürünlere net üzerinden orantılı" yap.
4. Doğrulama/düzeltme turunu ekle (maks. 3 tur, sonuçta fark ≠ 0 ise uyarı ver).
5. Gerçek vakalarla regresyon testi yaz: ürün 10121, AFC sepeti (155.000 hedefi), karışık sepet.