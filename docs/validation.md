# Doğrulama

## GitHub Actions

[Başarılı koşu · 13 Eylül 2026](https://github.com/nursimaotcu/kodarena/actions/runs/34733784585)

Commit: aff03d733f9d31e2c126e2f223feefaae4660cb1

- unit işi: Python testleri, Ruff kod/format ve JavaScript sözdizimi kontrolleri geçti.
- docker işi: 8 gerçek Linux Docker testi, API image build, Compose başlangıcı ve API + worker üzerinden gerçek HTTP smoke kontrolü geçti.
- Smoke akışı Python ve JavaScript için doğru cevap, yanlış cevap ve süre sınırı sonuçlarını kontrol eder.
- Docker testleri bellek ve çıktı sınırları, runtime hatası, root olmayan kullanıcı, dosya sistemi/ağ kısıtları ve iptal senaryolarını kapsar.

## Yerel kontrol

13 Eylül 2026 · Windows · Python 3.12

59 test geçti; 8 Docker testi yerelde motor bağlantısı olmadığı için atlanmıştı. Bu 8 test daha sonra yukarıdaki CI ortamında çalıştırıldı.

API ve kuyruk kontrollerinde gerçek SQLite dosyaları kullanıldı. Eşzamanlı claim, idempotency, lease kaybı, eski worker sonucunun reddi, heartbeat, iptal, yeniden deneme, kapasite, kalıcılık, olay imleci ve gizli test çıktıları kontrol edildi. CLI taşıma testleri gerçek konteyner testlerinden ayrıdır.

Gerçek Uvicorn sunucusunda tarayıcıdan giriş, problem yükleme, gönderim, detay ve iptal akışı denendi.

## Tekrarlama

Normal testler: python -m pytest -q

Docker motoru ve iki runtime image hazırken ARENA_DOCKER_TESTS=1 ile tests/test_docker.py çalıştırılır. API ve worker açıkken python scripts/smoke.py uçtan uca kontrolü yapar.

## Sınırlar

Başarılı CI koşusunda eski GitHub Action sürümlerinin Node çalışma zamanı için deprecation uyarıları bulunuyor. Yerel TestClient bağımlılıkları da iki deprecation uyarısı verdi. Bunlar test başarısızlığı değil.

Yük, uzun süreli dayanıklılık, container escape ve bağımsız güvenlik denetimi yapılmadı. Bu proje kontrollü yerel laboratuvardır; testlerin geçmesi herkese açık kod çalıştırma hizmeti güvenliği anlamına gelmez.
