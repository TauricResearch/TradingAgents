# TradingAgents Crypto — Kiến Trúc Hệ Thống Tổng Thể

## Mục tiêu

TradingAgents Crypto là một hệ thống hỗ trợ quyết định giao dịch crypto theo hướng **research first, trade second**.

- Nhận dữ liệu thị trường từ Binance và các nguồn phụ trợ
- Phát hiện setup tiềm năng bằng scanner
- Phân tích sâu để tạo signal
- Lưu toàn bộ kết quả vào memory theo tầng
- Chỉ dùng lesson đã lọc để phục vụ trade mode

---

## Nguyên tắc thiết kế

1. **Human luôn là người quyết định cuối cùng**
2. **Không dùng raw memory trực tiếp để ra quyết định trade**
3. **Tất cả mode đều ghi vào raw memory trước**
4. **Lesson chỉ được tạo sau khi lọc và tổng hợp**
5. **Trade mode chỉ đọc global lesson memory**
6. **Kiến trúc phải đơn giản, dễ debug, dễ mở rộng**

---

## Kiến trúc tổng quát

Hệ thống gồm 4 khối chính:

1. **Scanner**: quét thị trường và tìm setup đáng chú ý
2. **Analyzer**: phân tích sâu setup đã được trigger
3. **Memory Pipeline**: lưu raw, lọc lesson, đẩy lên global
4. **Execution / Notification**: gửi signal và vào lệnh khi có xác nhận

```text
Market Data → Scanner → Analyzer → Telegram → Human Confirm → Executor
                      ↘
                       Raw Memory → Lesson Processor → Global Memory → Trade Mode
```

---

## 2 mode vận hành

### Training mode

Mục đích:

- chạy không dùng tiền thật
- tạo dữ liệu
- lưu raw case
- hỗ trợ tạo lesson
- ưu tiên học và quan sát

### Trade mode

Mục đích:

- dùng tiền thật
- trade theo signal đã được lọc
- chỉ đọc global lesson memory
- ưu tiên an toàn và kỷ luật rủi ro

### Quan hệ giữa hai mode

- Training mode tạo nhiều dữ liệu hơn
- Trade mode dùng lesson đã lọc để ra quyết định
- Hai mode có thể chạy song song nhưng **không được trộn logic quyết định**

---

## Memory architecture

### 1) Raw memory

Raw memory lưu **toàn bộ log gốc** từ mọi mode.

Nội dung có thể gồm:

- thời gian
- mode
- strategy
- timeframe
- coin
- signal
- entry / exit
- result
- context thị trường
- reasoning
- notes

Raw memory có nhiệm vụ:

- audit
- debug
- truy vết
- làm nguồn dữ liệu cho xử lý tiếp theo

**Raw memory không dùng trực tiếp để trade.**

### 2) Lesson memory (Bản nháp bài học)

Lesson memory là **bản nháp bài học** - những pattern và insights cụ thể được rút ra từ raw data.

Đặc điểm của lesson:

- **Cụ thể**: gắn với một số case cụ thể, một strategy, một timeframe
- **Chưa tổng quát hóa**: có thể chỉ đúng trong điều kiện rất cụ thể
- **Đang được quan sát**: confidence có thể chưa cao, cần thêm dữ liệu
- **Có thể thay đổi**: khi có thêm evidence mới

Lesson memory lưu:

- pattern cụ thể từ 1 nhóm case
- điều kiện kích hoạt chi tiết
- kết luận ban đầu
- khuyến nghị thử nghiệm
- confidence (có thể thấp 0.5-0.7)
- số lượng case (ít, ~5-20)

**Lesson memory không dùng trực tiếp cho trade mode.**

### 3) Global memory (Bài học chính thức / Quy tắc dùng chung)

Global memory là **bài học chính thức** - những quy tắc đã được validate và áp dụng rộng rãi.

Đặc điểm của global lesson:

- **Tổng quát**: áp dụng được cho nhiều case, nhiều điều kiện tương tự
- **Đã validate**: được xác nhận từ nhiều nguồn (nhiều mode, nhiều strategy, nhiều timeframe)
- **Confidence cao**: thường >0.8, có bằng chứng mạnh
- **Ổn định**: không thay đổi thường xuyên
- **Production-ready**: an toàn để dùng cho trade mode

Đây là tầng mà:

- **trade mode đọc duy nhất**
- các mode khác có thể tham khảo
- dùng để tạo prompt / context / reflection

**Chỉ global memory được phép ảnh hưởng quyết định trade.**

### Luồng memory chuẩn

```text
All modes
   ↓
Raw memory (logs gốc)
   ↓
Memory processor
   ↓
Lesson memory (bản nháp, cụ thể, ~5-20 cases, confidence ~0.5-0.7)
   ↓
[Validation & Promotion Process]
   ↓
Global memory (chính thức, tổng quát, >30 cases, confidence >0.8)
   ↓
Trade mode reads ONLY here
```

### Quy trình promote lesson lên global

Một lesson chỉ được promote lên global khi:

1. **Đủ bằng chứng**: >30 cases từ nhiều nguồn (nhiều mode, nhiều coin, nhiều thời điểm)
2. **Confidence cao**: >0.8 (win rate rõ ràng, pattern ổn định)
3. **Cross-validated**: được confirm bởi ít nhất 2 mode khác nhau (vd: td1 và tr2)
4. **Tổng quát hóa được**: không quá cụ thể cho 1 coin hoặc 1 ngày cụ thể
5. **Human review**: nếu lesson ảnh hưởng lớn đến tiền thật

Before promote:

- Pattern chỉ đúng cho BTC trong tuần này
- "BTC breakout on Monday mornings often fails"

After promote:

- Pattern tổng quát cho nhiều coin, nhiều tuần
- "Breakout signals before major news events (Fed, CPI) have high failure rate regardless of technical indicators"

---

## Tại sao phải tách memory

Nếu gộp chung raw và lesson quá sớm, hệ thống có thể học nhầm.

Ví dụ:

- `td1` vào lệnh SELL sai ở một bối cảnh xấu
- `tr2` vào lệnh BUY đúng trong bối cảnh khác
- nếu gộp không có nhãn rõ ràng, trade mode có thể rút ra kết luận sai cho cả chiến lược

Tách memory giúp:

- không học lẫn giữa các mode
- không biến một case thua thành kết luận chung
- dễ kiểm tra hiệu quả từng strategy / timeframe / mode
- giảm nhiễu trước khi lên quyết định trade

---

## Memory processor

Memory processor là service xử lý raw → lesson → global.

Nhiệm vụ chính:

**Phase 1: Raw → Lesson (tạo bản nháp)**

1. đọc raw logs
2. chuẩn hóa dữ liệu
3. group theo strategy / timeframe / regime / direction
4. loại duplicate và noise
5. tính thống kê cơ bản
6. tạo lesson nháp nếu thấy pattern (~5+ cases tương tự)

**Phase 2: Lesson → Global (validate và promote)** 7. cross-validate lesson từ nhiều nguồn 8. tổng quát hóa pattern 9. tính confidence cuối cùng 10. promote lesson lên global nếu đạt ngưỡng 11. human review cho lessons quan trọng

### Cách xử lý hợp lý

- **Rule-based** để gom pattern ban đầu
- **Thống kê** để đánh giá độ tin cậy
- **LLM / model free** để tóm tắt và viết lesson
- **Human review** nếu lesson ảnh hưởng trade thật

### Mẫu rule đơn giản

- cùng strategy
- cùng timeframe
- cùng regime
- cùng direction
- cùng outcome pattern

### Khi nào tạo lesson (bản nháp)

Ngưỡng để tạo lesson nháp:

- **Tối thiểu 5-10 cases** tương tự
- Pattern lặp lại ít nhất 3 lần
- Win/loss rate lệch >60% hoặc <40%
- Confidence >0.5

→ Lesson lúc này chỉ là **hypothesis**, chưa dùng để trade

### Khi nào promote lên global (chính thức)

Ngưỡng để promote lên global:

- **>30 cases** từ nhiều nguồn
- Được confirm bởi ít nhất **2 mode** khác nhau
- Win/loss rate rõ ràng (>70% hoặc <30%)
- Confidence >0.8
- Có thể tổng quát hóa (không quá specific)
- Pass human review (nếu cần)

→ Global lesson là **rule**, dùng được cho trade mode

---

## Dữ liệu memory mẫu

### Raw record

```json
{
  "trade_id": "BTC_20250115_001",
  "mode_id": "td1",
  "strategy": "breakout",
  "timeframe": "5m",
  "coin": "BTC/USDT",
  "signal": "BUY",
  "entry": 67000,
  "exit": 64000,
  "result": "LOSS",
  "pnl": -3.0,
  "market_context": {
    "rsi": 27,
    "volume_spike": 2.3,
    "fear_greed": 25,
    "news": "Fed meeting tomorrow"
  },
  "reasoning": "RSI oversold, reversal expected",
  "reflection_candidate": "Avoid BUY signals 24h before Fed meetings regardless of RSI",
  "memory_tier": "raw"
}
```

### Lesson record (bản nháp)

```json
{
  "lesson_id": "lesson_draft_0042",
  "strategy": "breakout",
  "timeframe": "5m",
  "coin": "BTC/USDT",
  "condition": {
    "market_regime": "sideway",
    "volume": "low",
    "time_range": "2025-01-10 to 2025-01-15"
  },
  "lesson": "BTC breakout signals during low volume sideways on 5m chart failed 7/10 times this week.",
  "recommendation": "Consider skipping BTC 5m breakout when volume <1.5x average.",
  "confidence": 0.67,
  "evidence_count": 10,
  "source_modes": ["td1"],
  "memory_tier": "lesson",
  "status": "draft"
}
```

### Global record (chính thức)

```json
{
  "lesson_id": "global_rule_0007",
  "strategy": "breakout",
  "timeframe": "5m",
  "condition": {
    "market_regime": "sideway",
    "volume": "low"
  },
  "lesson": "Breakout trades in low-volume sideways markets have a high failure rate across all major coins.",
  "recommendation": "Avoid opening new breakout positions unless volume >2x average confirms momentum.",
  "confidence": 0.86,
  "evidence_count": 47,
  "source_modes": ["td1", "tr2", "td3"],
  "coins_tested": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
  "time_range": "2024-12 to 2025-01 (6 weeks)",
  "memory_tier": "global",
  "status": "validated",
  "reviewed_by": "human",
  "promoted_at": "2025-01-20"
}
```

---

## Scanner và Analyzer

### Scanner

Scanner có nhiệm vụ:

- quét coin theo timeframe ngắn
- tính indicators cơ bản
- tìm tín hiệu đủ mạnh để trigger analyzer
- giảm số lần gọi phân tích sâu

### Analyzer

Analyzer có nhiệm vụ:

- tổng hợp technical / sentiment / news / macro
- tạo signal có cấu trúc rõ ràng
- đẩy output sang Telegram
- ghi log vào raw memory

---

## Notification flow

### Telegram bot

Telegram bot chỉ là lớp trung gian để:

- gửi signal
- nhận confirm / skip
- theo dõi trạng thái lệnh

Bot không nên chứa logic quyết định chính.

### Executor

Executor chỉ chạy khi đã có confirm từ người dùng.

Quy trình:

1. nhận confirm
2. kiểm tra balance
3. tính size
4. đặt lệnh
5. đặt TP/SL
6. monitor kết quả
7. ghi kết quả vào raw memory

---

## Cấu trúc thư mục đề xuất

```text
tradingagents/
├── scanner/
│   └── fast_scanner.py
├── analyzer/
│   └── deep_analyzer.py
├── execution/
│   └── binance_executor.py
├── notifications/
│   └── telegram_bot.py
├── memory/
│   ├── raw/              # logs gốc từ tất cả mode
│   ├── lessons/          # bản nháp bài học (draft, specific)
│   ├── global/           # bài học chính thức (validated, general)
│   ├── memory_processor.py   # xử lý raw → lesson → global
│   ├── lesson_validator.py   # validate và promote lesson
│   └── trade_memory.py       # trade mode chỉ đọc global
├── dataflows/
│   ├── ccxt_provider.py
│   ├── coingecko_provider.py
│   └── indicators.py
├── config/
│   └── trading_config.py
└── main.py
```

---

## Cách dùng memory theo mode

### Tất cả mode

- đều ghi vào raw memory

### Training mode

- tạo nhiều raw case
- ưu tiên exploration
- hỗ trợ sinh lesson (bản nháp)
- có thể đọc cả lesson và global để học

### Trade mode

- **chỉ đọc global lesson** (bài học chính thức)
- **không đọc lesson nháp**
- không tự suy luận từ raw
- ưu tiên ổn định và an toàn

---

## Những phần không cần thiết đã lược bỏ

Để architecture gọn hơn, file này **không đi sâu** vào:

- danh sách model cụ thể
- chi phí API chi tiết
- roadmap theo tuần/tháng
- format Telegram quá dài
- cấu hình từng service nhỏ

Các phần đó có thể chuyển sang file config hoặc tài liệu triển khai riêng.

---

## Kết luận

Kiến trúc nên đi theo hướng:

- **Scanner để phát hiện setup**
- **Analyzer để đánh giá sâu**
- **Raw memory để lưu tất cả**
- **Lesson processor để lọc và chuẩn hóa**
- **Global memory để phục vụ trade mode**
- **Human quyết định cuối cùng**

Mục tiêu lớn nhất là:

> **không để bot học sai từ dữ liệu rác, và không để trade mode dùng raw case trực tiếp.**
