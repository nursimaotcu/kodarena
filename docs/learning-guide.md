# Projeyi anlatma ve deneme rehberi

## İlk çalıştırmada

1. API ve bir worker başlat; panelde aktif worker sayısını kontrol et.
2. Hazır toplam çözümünü gönder, olay sırasını ve test sonuçlarını aç.
3. Çözümü yanlış cevap verecek şekilde değiştir.
4. Sonsuz döngü göndererek süre sınırını dene.
5. İkinci worker başlat, birkaç iş gönder ve deneme sayılarını izle.

## Kodda takip edilecek yol

- arena/app.py: kimlik kontrolü, istek sınırı ve API sözleşmesi.
- arena/store.py: transaction, claim, heartbeat, sonuç kaydı ve iptal.
- arena/worker.py: HTTP koordinasyonu, heartbeat thread'i ve lease kaybı.
- arena/sandbox.py: kaynak sınırları, süreç yaşam döngüsü ve çıktı karşılaştırma.
- tests/test_api.py: eşzamanlı talepler, crash recovery ve kalıcılık.
- tests/test_docker.py: gerçek Linux konteyner sınırı.

## Açıklayabilmen gereken kararlar

**Worker bir işi aldıktan sonra kapanırsa?** Lease dolar. Başka worker claim yaptığında iş kurtarılır; üç denemeden sonra sonlanır.

**Eski worker geri dönerse?** Yeni token ile eşleşmediği için eski sonuç reddedilir.

**İş neden iki kez çalışabilir?** Koordinatör her zaman worker'ın gerçekten öldüğünü bilemez. Lease modeli ilerlemeyi sağlar ama tam olarak bir kez çalıştırma garantisi vermez.

**Neden stdout sınırsız toplanmıyor?** Çok çıktı üreten bir program worker belleğini doldurabilir. İki akış birlikte sınırlandırılır.

**Neden hidden test çıktısı saklanmıyor?** Program girdiyi tekrar yazdırabilir; çıktı üzerinden özel test verisi açığa çıkabilir.

**Neden Docker yeterli güvenlik iddiası değil?** Host kernel paylaşılır; daemon ve worker ayrı güçlü yetki sınırlarıdır.

**Neden SQLite?** Yerelde kurulumu kolaylaştırır ve transaction davranışı açıkça görülebilir. Çok makineli kullanım için tasarım değiştirilmelidir.

Bu soruları yalnızca ezberlemek yerine ilgili testi değiştirip sonucu gözlemlemek, projenin davranışını anlamayı kolaylaştırır.
