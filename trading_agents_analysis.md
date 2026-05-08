# TradingAgents Projesi Derinlemesine Analiz ve Çalışma Mantığı

Bu belge, **TradingAgents** projesinin mimarisini, Python dosyalarının işlevlerini ve sistemin genel çalışma mantığını detaylı olarak açıklamaktadır.

## 1. Sistemin Genel Çalışma Mantığı

TradingAgents, LangGraph (LangChain) üzerine inşa edilmiş, çoklu-ajanlı (multi-agent) bir finansal ticaret (trading) analiz ve karar alma çerçevesidir. Sistem, finansal bir varlığı (örneğin bir hisse senedini) farklı perspektiflerden analiz etmek üzere çeşitli uzman ajanları bir araya getirir.

Sistemin karar alma süreci **5 ana aşamadan** oluşan bir boru hattı (pipeline) şeklinde ilerler:

1. **Analist Ekibi (Analyst Team):** Piyasa, sosyal medya, haberler ve temel analiz (fundamentals) gibi farklı verileri toplayıp raporlar üretir.
2. **Araştırma Ekibi (Research Team):** Analistlerin raporlarını kullanarak Boğa (Bull) ve Ayı (Bear) araştırmacı ajanlar kendi aralarında tartışır. Araştırma Yöneticisi bu tartışmayı sentezleyip bir yatırım planı oluşturur.
3. **Ticaret Ekibi (Trading Team):** "Trader" ajanı, araştırma planına dayanarak somut bir al/sat/tut (Buy/Hold/Sell) eylemi ve potansiyel fiyat seviyelerini (giriş, zarar kesme) belirler.
4. **Risk Yönetim Ekibi (Risk Management):** Trader'ın teklifini Agresif, Nötr ve Muhafazakar ajanlar tartışarak risk analizini yapar.
5. **Portföy Yönetimi (Portfolio Management):** "Portfolio Manager" ajanı tüm süreci sentezleyip nihai portföy kararını (Ağırlık Artır, Tut, Sat vb.) ve yatırım tezini (Investment Thesis) net bir yapılandırılmış formatta verir.

---

## 2. Temel Dizinler ve Python Dosyalarının İşlevleri

### Ana Çalıştırma Dosyaları
* **`main.py`:** Projenin programatik olarak (kod üzerinden) çalıştırılmasını sağlayan temel giriş noktasıdır. Konfigürasyonu (veri sağlayıcıları, LLM modelleri) ayarlar, `TradingAgentsGraph` nesnesini başlatır ve belirli bir hisse senedi (örneğin NVDA) için `propagate` fonksiyonunu çağırarak tüm karar sürecini baştan sona işletir.
* **`cli/main.py`:** Sistemin komut satırı arayüzüdür (CLI). `typer` ve `rich` kütüphanelerini kullanarak kullanıcılara görsel açıdan zengin, adım adım sorular soran (Hisse adı, analiz tarihi, kullanılacak analistler, LLM sağlayıcısı vb.) ve ajansların çalışma durumlarını canlı bir şekilde konsolda gösteren bir yapıdır.

### `tradingagents/graph/` (Sistem Akışı ve LangGraph Altyapısı)
Bu dizin ajanların birbiriyle nasıl iletişim kurduğunu belirleyen iş akışı mantığını barındırır.
* **`trading_graph.py` (`TradingAgentsGraph`):** Sistemin beynidir. Kullanıcı konfigürasyonunu alır, LLM istemcilerini (hızlı ve derin düşünme için) oluşturur. Araç düğümlerini (tool nodes - örn: fiyat getirme, haber getirme) başlatır. Başlangıç durumunu oluşturarak LangGraph grafını tetikler ve durum güncellemelerini yönetir.
* **`setup.py` (`GraphSetup`):** LangGraph altyapısının kurulduğu yerdir. Hangi ajanların düğüm (node) olarak grafiğe ekleneceğini ve bu düğümler arasındaki bağlantıları (edge) tanımlar. Analistlerin sırayla çalışması, ardından Boğa/Ayı tartışmasına geçilmesi ve son olarak Portföy Yöneticisi'nde bitmesi gibi kuralları belirler.
* **`conditional_logic.py`:** Ajanlar arası geçişlerde kullanılacak koşullu mantığı barındırır (Örneğin tartışmaların kaç tur süreceği).
* **`checkpointer.py`:** Sistemin çalışması yarıda kesilirse diye süreçlerin kaydedilmesini (checkpointing) ve kalındığı yerden devam edilmesini sağlar.

### `tradingagents/agents/` (Ajan Tanımlamaları)
Farklı görevleri üstlenen yapay zeka ajanlarının (LLM promptlarının ve davranışlarının) tanımlandığı ana dizindir.
* **`schemas.py`:** Pydantic kullanılarak oluşturulmuş veri modelleridir. (Örneğin `PortfolioDecision`, `TraderProposal`, `ResearchPlan`). LLM'lerin sadece serbest metin üretmek yerine, yapılandırılmış (structured) JSON formatında karar ve özetler döndürmesini zorunlu kılar.
* **`analysts/` Dizi (Örn. `market_analyst.py`):** "Market Analyst" dosyası fiyat ve gösterge araçlarını (MACD, RSI vb.) çağırarak piyasanın teknik durumunu analiz eden prompt'ları ve mantığı içerir. Benzer şekilde News ve Fundamentals analistleri de kendi alanlarında veri çeker.
* **`researchers/` Dizi (Örn. `bull_researcher.py`, `bear_researcher.py`):** Boğa ajanı pozitif yönleri arayıp alım yönünde argümanlar sunarken, Ayı ajanı negatif yönlere odaklanır.
* **`managers/portfolio_manager.py`:** Sistemdeki en yetkili karar mercidir. Gelen bütün analizleri, araştırma planlarını ve risk tartışmalarını okur. Pydantic şemasını (`PortfolioDecision`) kullanarak net bir Rating (Buy, Hold, Sell), Yönetici Özeti ve Yatırım Tezi çıkartır.
* **`trader/trader.py`:** Yatırım planını alıp bunu doğrudan emirlere (Giriş noktası, Stop-loss noktası, Pozisyon büyüklüğü) döken aksiyon odaklı ajandır.
* **`risk_mgmt/` Dizi:** Trader'ın kararının risklerini farklı iştah profillerine (Agresif, Nötr, Muhafazakar) göre tartışan ajanlar.

### `tradingagents/dataflows/` (Veri Akışı ve Araçlar)
LLM ajanlarının gerçek dünya verilerine erişmesini sağlayan araçların (Tools) bulunduğu kısımdır.
* **`y_finance.py` ve `alpha_vantage_*.py`:** Yahoo Finance ve Alpha Vantage API'lerinden hisse geçmiş verisi, temel veriler (bilanço, gelir tablosu), haberler ve indikatör verilerini çekmek için kullanılan servislerdir.
* **`utils.py` & `stockstats_utils.py`:** Verileri ajanların anlayabileceği temiz bir metin (Markdown/CSV formatı) veya indikatör formuna getiren yardımcı fonksiyonlardır.

### `tradingagents/llm_clients/` (Dil Modeli Entegrasyonları)
* **`openai_client.py`, `anthropic_client.py`, `google_client.py`, `base_client.py`, `factory.py`:** Sistemin LLM bağımsız (LLM-agnostic) çalışmasını sağlayan katmandır. OpenAI, Anthropic, Google Gemini veya Azure gibi farklı sağlayıcıları standartlaştırarak sistemin `create_llm_client()` fonksiyonuyla tek bir standart tip LLM kullanıyormuş gibi hareket etmesini sağlar.

---

## 3. Çalışma Mantığı Özeti

1. **İstek ve Veri Toplama:** Sisteme bir hisse kodu (örn. SPY) ve tarih verilir. Sistem `analysts` içindeki ajanları tetikler. Bu ajanlar `dataflows` içindeki fonksiyonları bir Tool (Araç) olarak kullanarak API'lerden veri (fiyat, bilanço, haber) çeker ve raporlar yazar.
2. **Yorumlama ve Tartışma:** Tüm analist raporları bir metinde (State) toplanır. `researchers` ve `risk_mgmt` ajanları bu biriken metni okuyarak birbirleriyle simüle edilmiş bir münazara yaparlar.
3. **Karar Alma:** Tartışmaların ardından `portfolio_manager.py` içindeki ajan devreye girer. Promptu sayesinde tüm geçmiş tartışmaları değerlendirir ve `schemas.py` dosyasındaki Pydantic modeline uygun kesin bir sonuç çıktısı üretir. Bu çıktı dosyaya loglanır ve CLI üzerinden kullanıcıya şık bir rapor halinde sunulur.

Sistem, LangGraph mimarisini kullanarak ajanlar arası bir durum makinesi (state machine) gibi çalışır ve adımları modüler şekilde zincirler.
