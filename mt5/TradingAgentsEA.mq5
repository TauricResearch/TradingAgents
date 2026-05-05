#property strict

#include <Trade/Trade.mqh>

CTrade trade;

input string SignalFileName = "tradingagents_signal.json";
input bool UseCommonFiles = true;
input long MagicNumber = 26052026;
input int PollSeconds = 2;
input int MaxPositions = 2;
input double MaxDailyLossUsd = 40.0;

datetime last_read_time = 0;

string ReadAllText(const string file_name, const bool common)
{
   int flags = FILE_READ | FILE_TXT;
   if(common) flags |= FILE_COMMON;
   int handle = FileOpen(file_name, flags);
   if(handle == INVALID_HANDLE) return "";
   string text = "";
   while(!FileIsEnding(handle))
   {
      text += FileReadString(handle);
      if(!FileIsEnding(handle)) text += "\n";
   }
   FileClose(handle);
   return text;
}

string JsonGetString(const string json, const string key)
{
   string k = "\"" + key + "\"";
   int p = StringFind(json, k);
   if(p < 0) return "";
   p = StringFind(json, ":", p);
   if(p < 0) return "";
   p++;
   while(p < StringLen(json) && (StringGetCharacter(json, p) == ' ' || StringGetCharacter(json, p) == '\t' || StringGetCharacter(json, p) == '\r' || StringGetCharacter(json, p) == '\n')) p++;
   if(p >= StringLen(json)) return "";
   if(StringGetCharacter(json, p) != '\"') return "";
   p++;
   int e = StringFind(json, "\"", p);
   if(e < 0) return "";
   return StringSubstr(json, p, e - p);
}

double JsonGetNumber(const string json, const string key, const double def)
{
   string k = "\"" + key + "\"";
   int p = StringFind(json, k);
   if(p < 0) return def;
   p = StringFind(json, ":", p);
   if(p < 0) return def;
   p++;
   while(p < StringLen(json) && (StringGetCharacter(json, p) == ' ' || StringGetCharacter(json, p) == '\t' || StringGetCharacter(json, p) == '\r' || StringGetCharacter(json, p) == '\n')) p++;
   if(p >= StringLen(json)) return def;
   int e = p;
   while(e < StringLen(json))
   {
      ushort c = (ushort)StringGetCharacter(json, e);
      if((c >= '0' && c <= '9') || c == '.' || c == '-' || c == '+') { e++; continue; }
      break;
   }
   string s = StringSubstr(json, p, e - p);
   if(StringLen(s) == 0) return def;
   return StringToDouble(s);
}

bool JsonGetBool(const string json, const string key, const bool def)
{
   string k = "\"" + key + "\"";
   int p = StringFind(json, k);
   if(p < 0) return def;
   p = StringFind(json, ":", p);
   if(p < 0) return def;
   p++;
   while(p < StringLen(json) && (StringGetCharacter(json, p) == ' ' || StringGetCharacter(json, p) == '\t' || StringGetCharacter(json, p) == '\r' || StringGetCharacter(json, p) == '\n')) p++;
   if(p + 4 <= StringLen(json) && StringSubstr(json, p, 4) == "true") return true;
   if(p + 5 <= StringLen(json) && StringSubstr(json, p, 5) == "false") return false;
   return def;
}

int CurrentDayKey()
{
   MqlDateTime t;
   TimeToStruct(TimeCurrent(), t);
   return t.year * 10000 + t.mon * 100 + t.day;
}

double ClosedProfitSinceDayStart()
{
   MqlDateTime t;
   TimeToStruct(TimeCurrent(), t);
   t.hour = 0; t.min = 0; t.sec = 0;
   datetime from = StructToTime(t);
   datetime to = TimeCurrent();
   if(!HistorySelect(from, to)) return 0.0;

   double profit = 0.0;
   int total = HistoryDealsTotal();
   for(int i=0;i<total;i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0) continue;
      string sym = (string)HistoryDealGetString(ticket, DEAL_SYMBOL);
      if(sym != _Symbol) continue;
      long magic = (long)HistoryDealGetInteger(ticket, DEAL_MAGIC);
      if(magic != MagicNumber) continue;
      long entry = (long)HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_OUT) continue;
      profit += HistoryDealGetDouble(ticket, DEAL_PROFIT) + HistoryDealGetDouble(ticket, DEAL_SWAP) + HistoryDealGetDouble(ticket, DEAL_COMMISSION);
   }
   return profit;
}

int CountOpenPositions()
{
   int n = 0;
   for(int i=0;i<PositionsTotal();i++)
   {
      if(!PositionSelectByIndex(i)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      n++;
   }
   return n;
}

int CountPendingOrders()
{
   int n = 0;
   for(int i=0;i<OrdersTotal();i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS)) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol) continue;
      if((long)OrderGetInteger(ORDER_MAGIC) != MagicNumber) continue;
      long type = (long)OrderGetInteger(ORDER_TYPE);
      if(type == ORDER_TYPE_BUY_LIMIT || type == ORDER_TYPE_BUY_STOP || type == ORDER_TYPE_SELL_LIMIT || type == ORDER_TYPE_SELL_STOP)
         n++;
   }
   return n;
}

double RoundVolume(double vol)
{
   double minv = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxv = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0) step = 0.01;
   if(vol < minv) vol = minv;
   if(vol > maxv) vol = maxv;
   double k = MathFloor(vol / step);
   return NormalizeDouble(k * step, 2);
}

double ComputeLotsFromRiskUsd(double entry, double sl, double risk_usd)
{
   double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick_value <= 0 || tick_size <= 0) return 0.0;
   double dist = MathAbs(entry - sl);
   if(dist <= 0) return 0.0;
   double loss_per_lot = (dist / tick_size) * tick_value;
   if(loss_per_lot <= 0) return 0.0;
   double lots = risk_usd / loss_per_lot;
   return RoundVolume(lots);
}

bool PlacePending(const string pending_type, double entry, double sl, double tp, double risk_usd, const string comment)
{
   if(entry <= 0 || sl <= 0) return false;
   ENUM_ORDER_TYPE type = ORDER_TYPE_BUY_STOP;
   if(pending_type == "BUY_STOP") type = ORDER_TYPE_BUY_STOP;
   else if(pending_type == "BUY_LIMIT") type = ORDER_TYPE_BUY_LIMIT;
   else if(pending_type == "SELL_STOP") type = ORDER_TYPE_SELL_STOP;
   else if(pending_type == "SELL_LIMIT") type = ORDER_TYPE_SELL_LIMIT;
   else return false;

   double lots = ComputeLotsFromRiskUsd(entry, sl, risk_usd);
   if(lots <= 0) return false;

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetTypeFilling(ORDER_FILLING_FOK);
   bool ok = trade.OrderSend(_Symbol, type, lots, entry, 0.0, sl, tp, comment);
   return ok;
}

void ManageTrailingFromSignal(const string json)
{
   bool enabled = false;
   int p = StringFind(json, "\"trailing\"");
   if(p >= 0)
   {
      int obj_end = StringFind(json, "}", p);
      if(obj_end > p)
      {
         string sub = StringSubstr(json, p, obj_end - p + 1);
         enabled = JsonGetBool(sub, "enabled", false);
         double mult = JsonGetNumber(sub, "multiplier", 0.0);
         double atr = JsonGetNumber(sub, "atr", 0.0);
         double activate_after_r = JsonGetNumber(sub, "activate_after_R", 1.0);
         if(!enabled || mult <= 0 || atr <= 0) return;

         double entry_price = JsonGetNumber(json, "entry_price", 0.0);
         double stop_loss = JsonGetNumber(json, "stop_loss", 0.0);
         if(entry_price <= 0 || stop_loss <= 0) return;
         double r = MathAbs(entry_price - stop_loss);
         if(r <= 0) return;

         for(int i=0;i<PositionsTotal();i++)
         {
            if(!PositionSelectByIndex(i)) continue;
            if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
            if((long)PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
            long ptype = (long)PositionGetInteger(POSITION_TYPE);
            double price_open = PositionGetDouble(POSITION_PRICE_OPEN);
            double sl = PositionGetDouble(POSITION_SL);
            double tp = PositionGetDouble(POSITION_TP);

            double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
            double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            double move = 0.0;
            if(ptype == POSITION_TYPE_BUY) move = bid - price_open;
            else move = price_open - ask;
            if(move < activate_after_r * r) continue;

            double new_sl = sl;
            if(ptype == POSITION_TYPE_BUY) new_sl = bid - mult * atr;
            else new_sl = ask + mult * atr;
            new_sl = NormalizeDouble(new_sl, (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS));

            if(ptype == POSITION_TYPE_BUY && new_sl > sl) trade.PositionModify(_Symbol, new_sl, tp);
            if(ptype == POSITION_TYPE_SELL && (sl == 0.0 || new_sl < sl)) trade.PositionModify(_Symbol, new_sl, tp);
         }
      }
   }
}

int OnInit()
{
   EventSetTimer(PollSeconds);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   if(ClosedProfitSinceDayStart() <= -MaxDailyLossUsd) return;

   string json = ReadAllText(SignalFileName, UseCommonFiles);
   if(StringLen(json) <= 0) return;

   datetime now = TimeCurrent();
   if(now - last_read_time < PollSeconds) {}
   last_read_time = now;

   string sym = JsonGetString(json, "symbol");
   if(sym != _Symbol) return;

   string action = JsonGetString(json, "action");
   if(action == "HOLD") { ManageTrailingFromSignal(json); return; }

   int max_pos = (int)JsonGetNumber(json, "max_positions", (double)MaxPositions);
   if(CountOpenPositions() + CountPendingOrders() >= max_pos) { ManageTrailingFromSignal(json); return; }

   string pending_type = JsonGetString(json, "pending_type");
   double entry = JsonGetNumber(json, "entry_price", 0.0);
   double sl = JsonGetNumber(json, "stop_loss", 0.0);
   double tp2 = JsonGetNumber(json, "take_profit_2", 0.0);
   double risk_usd = JsonGetNumber(json, "risk_usd", 10.0);
   string comment = JsonGetString(json, "comment");
   if(StringLen(comment) == 0) comment = "tradingagents";

   double stop_level = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(pending_type == "BUY_STOP" && entry < ask + stop_level) return;
   if(pending_type == "SELL_STOP" && entry > bid - stop_level) return;
   if(pending_type == "BUY_LIMIT" && entry > ask - stop_level) return;
   if(pending_type == "SELL_LIMIT" && entry < bid + stop_level) return;

   PlacePending(pending_type, entry, sl, tp2, risk_usd, comment);
   ManageTrailingFromSignal(json);
}
