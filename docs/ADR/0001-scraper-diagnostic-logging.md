# ADR-0001: Scraper Tanılama Loglarının Detaylandırılması

- **Durum:** Accepted
- **Tarih:** 2026-11-01
- **Karar sahipleri:** Proje ekibi
- **Kapsam:** Employee-triggered scraper ve scrape progress görünürlüğü

## Bağlam

Mevcut loglar kategori tamamlandığında özet bilgi veriyor; ancak bir kategori
uzun sürdüğünde beklemenin HTTP isteğinden, retry/backoff'tan, HTML parse
işleminden veya pagination'dan kaynaklandığı ayırt edilemiyor.

## Karar

Bu ADR kabul edilmiştir. Scraper; crawl oturumu, request, sitemap discovery,
kategori/sayfa ve parser aşamalarını süre, durum ve sayaçlarla loglayacaktır.
Response body, cookie ve hassas header bilgileri loglanmayacaktır.

## Sonuçlar

- Tanılama logları mevcut rotating log dosyasına yazılacaktır.
- Başarılı ayrıntılı olaylar `DEBUG`, yavaş veya başarısız olaylar `WARNING`,
  crawl özetleri `INFO` seviyesinde tutulacaktır.
- Kullanıcı arayüzü kategori tamamlanmasını beklemeden sayfa/aşama ilerlemesini
  gösterecektir.
- Scraper iş mantığı, rate limit kuralları ve retry limitleri değişmeyecektir.

## Plan: Scraper Tanılama Loglarını Detaylandırma

Amaç, özellikle `4k-ultima-tv` gibi uzun süren kategorilerde gecikmenin HTTP isteğinden mi, retry/backoff’tan mı, HTML parse işleminden mi yoksa pagination’dan mı kaynaklandığını loglardan ayırt etmek.

### Adımlar

1. **Crawl oturumu için korelasyon bilgisi ekleme**
   - Her crawl için kısa bir `run_id` üretilecek.
   - Log mesajlarında kategori, sayfa ve `run_id` bilgileri kullanılacak.
   - Hassas response içeriği veya tam HTML loglanmayacak.

2. **HTTP isteklerini ayrıntılı loglama**
   - `crawler.py` içindeki `_Fetcher.get` için:
     - URL/kategori/sayfa bağlamı
     - deneme numarası
     - istek süresi
     - HTTP status
     - response byte uzunluğu
     - retry nedeni
     - backoff süresi
     - 403/429 bloklanma streak’i
     - cancellation
   - Başarılı istekler için `DEBUG`, yavaş istekler ve retry’lar için `WARNING` kullanılacak.

3. **Sitemap discovery aşamasını görünür hale getirme**
   - Sitemap index başlangıç/bitiş süreleri.
   - Bulunan product sitemap sayısı.
   - Sitemap başına URL sayısı ve başarısız istekler.
   - Toplam product URL ve kategori sayısı.
   - Böylece ilk kategori başlamadan önceki gecikmeler ayırt edilebilecek.

4. **Kategori ve sayfa yaşam döngüsünü loglama**
   - `_crawl_category` içinde her kategori/sayfa için:
     - fetch başlangıcı ve bitişi
     - parse başlangıcı ve bitişi
     - HTML byte sayısı
     - bulunan kart sayısı
     - yeni ürün sayısı
     - duplicate/repeated page veya empty page ile bitiş nedeni
     - sayfa ve kategori toplam süresi
   - `parse_listing` çevresindeki süre ayrıca ölçülecek; böylece “HTTP hızlı ama parser yavaş” durumu açıkça görülecek.
   - Belirli eşik üzerindeki parse veya request süreleri ayrıca `WARNING` olarak yazılacak.

5. **İlerleme bilgisini sayfa/phase seviyesine genişletme**
   - `models.py` içindeki `ScrapeProgress` yapısına mevcut davranışı bozmayacak şekilde:
     - phase
     - page
     - current URL veya güvenli URL bilgisi
     - kategori içi ürün sayısı
     alanları eklenecek.
   - `scrape_worker.py` ve `update_dialog.py` bu ilerlemeyi kullanacak.
   - Uzun süren kategorilerde çalışan işlem artık GUI’de “takılmış” görünmeyecek.

6. **Crawl sonucu ve worker loglarını zenginleştirme**
   - `crawler.py` final özetine:
     - toplam request
     - retry sayısı
     - toplam sayfa
     - discovery süresi
     - parse süresi
     - price failure
     - nameless card
     - capped category
     sayaçları eklenecek.
   - `scrape_worker.py` başlangıç, cancellation, başarı ve hata loglarıyla tamamlanacak.
   - `scrape_state.py` gate logları crawl `run_id` ile ilişkilendirilecek; mevcut cooldown/quota davranışı değiştirilmeyecek.

7. **Davranış odaklı testler ekleme**
   - `test_scraper.py`:
     - request retry/status/süre logları
     - parse süresi logu
     - kategori/sayfa ilerleme bilgisi
     - empty/repeated/capped/failed page ayrımı
     - discovery sayaçları
   - Timing testleri gerçek süreye bağlanmayacak; clock/monkeypatch veya kontrollü fake fonksiyonlarla doğrulanacak.
   - Mevcut saf parser testleri timing ayrıntılarına bağımlı hale getirilmeyecek.

8. **Dokümantasyonu güncelleme**
   - `implement_scrapping.md`:
     - sayfa ve parser aşaması ilerlemesi
     - request/retry/response-size logları
     - uzun süren kategori teşhis akışı
     - log dosyasının konumu
     - response body loglanmadığı ve hassas veri korunacağı
   - Gerekirse `README.md` içine log dosyasını inceleme yönergesi eklenecek.

### Kapsam dışı

- Scraper’ın iş mantığı, rate-limit kuralları veya retry limitleri değiştirilmeyecek.
- Response body, cookie, header veya kişisel/hassas veri loglanmayacak.
- Yavaşlığı çözmeye yönelik performans optimizasyonu bu çalışmada yapılmayacak; önce ölçülebilir teşhis altyapısı kurulacak.

### Doğrulama

1. Hedefli scraper testleri çalıştırılacak.
2. Logging testlerinde mesajların kategori, sayfa, aşama, status ve süre bilgilerini içerdiği doğrulanacak.
3. UI testleriyle sayfa/phase ilerlemesinin mevcut kategori ilerlemesini bozmadığı kontrol edilecek.
4. Ruff/type-check mevcut proje komutlarıyla çalıştırılacak.
5. Kontrollü bir crawl logunda `4k-ultima-tv` için fetch ve parse sürelerinin ayrı ayrı görüldüğü doğrulanacak.
