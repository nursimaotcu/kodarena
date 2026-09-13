# Doğrulama

13 Eylül 2026 · Windows · Python 3.12

## Geçen kontroller

- **59 test geçti.** API, gerçek SQLite dosyalarıyla kuyruk davranışı, değerlendirme mantığı, worker koordinasyonu ve sahte Docker CLI taşımasıyla süreç yönetimi kontrol edildi.
- Ruff kod ve format kontrolleri geçti.
- JavaScript sözdizimi kontrolü geçti.
- Docker Compose yapılandırması parse edildi.
- GitHub yükleme PowerShell dosyası parse edildi.
- Gerçek Uvicorn sunucusunda tarayıcıdan giriş, problem yükleme, kod gönderme, kuyruk detayını açma ve gönderimi iptal etme akışı çalıştı. Worker sayısı doğru biçimde 0 gösterildi; çalışmamış kod için başarılı sonuç üretilmedi.

Testlerin kapsadığı başlıca davranışlar:

- Eşzamanlı aynı isteğin tek iş oluşturması.
- Eşzamanlı claim sırasında yalnızca bir worker'ın işi alması.
- Süresi dolan lease ve eski worker sonucunun reddedilmesi.
- Heartbeat ile süre uzatma; iptalin tamamlanmış sonuç tarafından ezilememesi.
- Üç denemeden sonra altyapı hatasıyla sonlandırma.
- Kuyruk kapasitesi, kalıcılık, olay imleci ve sayfalama.
- Gizli test çıktısının worker'dan gönderilmemesi ve API'nin ayrıca temizlemesi.
- Çıktı bütçesi, timeout sırasında kill, OOM verdict ve cleanup çağrıları. Bu son grubun yerel testi gerçek konteyner yerine sahte CLI taşıması kullanır.

## Henüz çalıştırılmayan kontroller

**8 gerçek Docker testi atlandı.** Docker CLI kurulu olsa da Linux Docker Engine bağlantısı kurulamadı. Dolayısıyla gerçek Python/JavaScript konteyner yürütmesi, OOM, ağ izolasyonu, salt okunur dosya sistemi ve konteyner iptali bu makinede doğrulanmadı.

API image build, Compose ile çalışan API ve gerçek worker üzerinden scripts/smoke.py henüz çalıştırılmadı. GitHub Actions yapılandırması bunları ayrı docker işinde çalıştıracak şekilde hazırlandı; yayımlanmış başarılı bir CI koşusu henüz yok.

Gerçek sınırları doğrulamak için Docker Engine ve runtime image'leri hazırken:

~~~powershell
$env:ARENA_DOCKER_TESTS = "1"
python -m pytest tests/test_docker.py -q
~~~

Bu komutta motor hazır değilse testler başarısız olur; sahte çalıştırmaya dönülmez.

## Test ortamı notları

TestClient bağımlılıklarında iki deprecation uyarısı var: Starlette / HTTPX geçişi ve AnyIO BlockingPortal alias'ı. Uyarılar gizlenmedi; test başarısızlığı değiller.

Windows sandbox'ta sistemin ortak pytest geçici klasörüne erişim olmadığı için testlerde çalışma klasörü altında yeni ve izole bir geçici dizin kullanıldı. Kullanıcı kurulumunda normal pytest komutu yeterlidir.

Yük, uzun süreli dayanıklılık, container escape ve bağımsız güvenlik denetimi yapılmadı. Geçen birim testleri bu kontrollerin yerine geçmez.
