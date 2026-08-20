"""KAP analyst for material BIST public disclosures."""

from __future__ import annotations

from datetime import date, timedelta

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import get_instrument_context_from_state
from tradingagents.agents.utils.kap_data_tools import get_kap_disclosures
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.kap import is_bist_ticker


def create_kap_analyst(llm):
    def kap_analyst_node(state):
        ticker = state["company_of_interest"]
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)

        if not is_bist_ticker(ticker):
            report = (
                "KAP Görünümü: UYGULANAMAZ\n\n"
                "Bu araç yalnızca `.IS` uzantılı Borsa İstanbul hisselerinde çalışır. "
                "Karar diğer analist raporlarıyla devam etmelidir."
            )
            return {
                "messages": [AIMessage(content=report)],
                "kap_report": report,
            }

        try:
            end = date.fromisoformat(current_date)
        except ValueError:
            end = date.today()
        lookback_days = int(get_config().get("kap_lookback_days", 30))
        start = end - timedelta(days=lookback_days)
        tools = [get_kap_disclosures]

        system_message = f"""Sen ARVEN TRADE KAP Analistisin. Yalnızca KAP bildirimlerini yatırım açısından değerlendir; sadece özetleme yapma.

Önce get_kap_disclosures aracını tam olarak şu tarih aralığıyla çağır: başlangıç {start.isoformat()}, bitiş {end.isoformat()}. Ticker olarak `.IS` uzantısını koru. Araç yapılandırılmış JSON döndürür. Ham metni tekrar etme; metadata ve kısa özetle yetin.

Finansal sonuç, satış/ciro, kârlılık, yatırım, kapasite, sözleşme/ihale, satın alma/birleşme/bölünme, temettü, sermaye artırımı, geri alım, borçlanma/finansman, dava/ceza/düzenleyici işlem, yönetim/ortaklık/pay satışı, faaliyet veya üretim kesintisi ve kredi derecelendirmesine özellikle dikkat et.

Her önemli bildirimi POZİTİF / HAFİF POZİTİF / NÖTR / HAFİF NEGATİF / NEGATİF ve DÜŞÜK / ORTA / YÜKSEK / KRİTİK olarak sınıflandır. KAP tek başına nihai işlem kararı değildir.

Yanıtı sade ve kısa Türkçe yaz. Şu düzeni kullan:
KAP Görünümü: OLUMLU / NÖTR / OLUMSUZ / VERİ YOK
Etki Skoru: -100 ile +100
Önemli Bildirim: sayı
Kritik Bildirim: sayı
Son Bildirim: tarih veya yok
Kısa Özet: en çok iki cümle
Önemli Bildirimler: en fazla 10 madde; tarih, konu, etki, önem, kısa gerekçe ve KAP URL.

Araç hata veya erişilememe durumu döndürürse bunu açıkça söyle ve diğer analizlerin devam etmesi gerektiğini belirt. Veri uydurma.

{instrument_context}"""

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Mevcut tek veri aracını kullan ve ardından kısa KAP raporunu üret. "
                    "Bugünün analiz tarihi {current_date}. {system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        ).partial(current_date=current_date, system_message=system_message)

        result = (prompt | llm.bind_tools(tools)).invoke(state["messages"])
        report = result.content if not result.tool_calls else ""
        return {"messages": [result], "kap_report": report}

    return kap_analyst_node
