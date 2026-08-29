type Tester={
  tester_code:string; telegram_chat_id:number; locations:string[]; voivodeships:string[];
  max_price:number; min_area:number; max_area:number; min_rooms:number; max_rooms:number;
  max_price_m2:number|null; min_market_discount_pct:number|null; flip_analysis_enabled:boolean; exclusions:string[];
};
type Candidate={
  source:string; source_offer_id:string; title:string|null; url:string; city:string|null; voivodeship:string|null;
  price:number|null; area:number|null; rooms:number|null; price_m2:number|null; floor_text:string|null; description:string|null;
  market_price_m2:number|null; market_discount_pct:number|null; suggested_purchase_price:number|null;
  renovation_cost_low:number|null; renovation_cost_high:number|null; suggested_sale_price:number|null;
  estimated_profit_low:number|null; estimated_profit_high:number|null; analysis_confidence:string|null; last_seen_at:string;
};
const json=(data:unknown,status=200)=>new Response(JSON.stringify(data),{status,headers:{"content-type":"application/json; charset=utf-8"}});
const money=(value:number|null)=>value==null?"brak danych":Math.round(value).toLocaleString("pl-PL")+" zł";
const norm=(value:unknown)=>String(value||"").toLowerCase().normalize("NFKC").replace(/\s+/g," ").trim();
const warsawDate=(date:Date)=>new Intl.DateTimeFormat("en-CA",{timeZone:"Europe/Warsaw",year:"numeric",month:"2-digit",day:"2-digit"}).format(date);
const warsawHour=(date:Date)=>Number(new Intl.DateTimeFormat("en-GB",{timeZone:"Europe/Warsaw",hour:"2-digit",hourCycle:"h23"}).format(date));
async function telegram(token:string,method:string,body:unknown){
  const response=await fetch("https://api.telegram.org/bot"+token+"/"+method,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok||!data.ok)throw new Error("telegram_"+method+"_failed");
  return data.result;
}
async function db(path:string,key:string,init:RequestInit={}){
  const base=Deno.env.get("SUPABASE_URL")!;
  return fetch(base+"/rest/v1/"+path,{...init,headers:{apikey:key,authorization:"Bearer "+key,"content-type":"application/json",...(init.headers||{})}});
}
async function rows(path:string,key:string){
  const response=await db(path,key);
  if(!response.ok)throw new Error("db_read_"+response.status);
  return response.json();
}
function matches(t:Tester,o:Candidate){
  const locations=t.locations||[],regions=t.voivodeships||[];
  if((locations.length||regions.length)&&!locations.includes(o.city||"")&&!regions.includes(o.voivodeship||""))return false;
  if(o.price==null||o.price>t.max_price)return false;
  if(o.area==null||o.area<Number(t.min_area)||o.area>Number(t.max_area))return false;
  if(o.rooms==null||o.rooms<t.min_rooms||o.rooms>t.max_rooms)return false;
  if(t.max_price_m2!=null&&(o.price_m2==null||o.price_m2>t.max_price_m2))return false;
  if(t.min_market_discount_pct!=null&&(o.market_discount_pct==null||o.market_discount_pct<Number(t.min_market_discount_pct)))return false;
  const hay=norm((o.title||"")+" "+(o.description||"")+" "+(o.floor_text||""));
  for(const exclusion of t.exclusions||[]){const value=norm(exclusion);if(value&&hay.includes(value))return false;}
  return true;
}
function offerMessage(o:Candidate,showAnalysis:boolean){
  const negotiated=o.suggested_purchase_price??(o.price==null?null:Math.round(o.price*0.95));
  return [
    "🔥 NOWA OFERTA SPEŁNIAJĄCA KRYTERIA FLIPA",
    "",
    "🌐 "+o.source,
    "📍 "+(o.city||"lokalizacja nieustalona")+(o.voivodeship?" | woj. "+o.voivodeship:""),
    "🏠 "+(o.area??"?")+" m² | "+(o.rooms??"?")+" pok.",
    "💰 Cena ofertowa: "+money(o.price),
    "🤝 Sugerowana cena zakupu po negocjacjach: "+money(negotiated),
    "📐 "+(o.price_m2==null?"brak ceny/m²":Math.round(o.price_m2).toLocaleString("pl-PL")+" zł/m²"),
    o.floor_text?"🏢 "+o.floor_text:"",
    "",
    o.title||"Oferta mieszkania",
    "",
    showAnalysis?"📊 ANALIZA OPŁACALNOŚCI FLIPA":"",
    showAnalysis&&o.market_price_m2!=null?"Cena rynkowa: "+Math.round(o.market_price_m2).toLocaleString("pl-PL")+" zł/m²":"",
    showAnalysis&&o.market_discount_pct!=null?"Rabat do rynku: "+Number(o.market_discount_pct).toLocaleString("pl-PL",{maximumFractionDigits:1})+"%":"",
    showAnalysis&&o.renovation_cost_low!=null&&o.renovation_cost_high!=null?"Szacowany remont/odświeżenie: "+money(o.renovation_cost_low)+" – "+money(o.renovation_cost_high):"",
    showAnalysis&&o.suggested_sale_price!=null?"Sugerowana cena sprzedaży: "+money(o.suggested_sale_price):"",
    showAnalysis&&o.estimated_profit_low!=null&&o.estimated_profit_high!=null?"Szacowany zysk: "+money(o.estimated_profit_low)+" – "+money(o.estimated_profit_high):"",
    showAnalysis&&o.analysis_confidence?"Pewność analizy: "+o.analysis_confidence:"",
    "",
    "🔗 "+o.url,
    "",
    "Analiza jest szacunkowa i nie stanowi wyceny ani gwarancji zysku."
  ].filter(Boolean).join("\n");
}
async function alreadyDelivered(key:string,tester:string,source:string,offerId:string){
  const path="deliveries?select=tester_code&tester_code=eq."+encodeURIComponent(tester)+"&source=eq."+encodeURIComponent(source)+"&source_offer_id=eq."+encodeURIComponent(offerId)+"&limit=1";
  return (await rows(path,key)).length>0;
}
async function recordDelivery(key:string,tester:string,source:string,offerId:string,messageId:number){
  const response=await db("deliveries",key,{method:"POST",headers:{Prefer:"return=minimal"},body:JSON.stringify({tester_code:tester,source,source_offer_id:offerId,telegram_message_id:messageId})});
  if(!response.ok)throw new Error("delivery_insert_"+response.status);
}
Deno.serve(async(req)=>{
  try{
    if(req.method!=="POST")return json({error:"method_not_allowed"},405);
    const botToken=req.headers.get("x-telegram-bot-token")||"";
    if(!botToken)return json({error:"missing_bot_token"},401);
    const me=await telegram(botToken,"getMe",{});
    if(String(me?.username||"").toLowerCase()!=="radarokazjibot")return json({error:"wrong_bot"},403);
    const body=await req.json().catch(()=>({}));
    const mode=body?.mode==="summary"?"summary":"alerts";
    const dryRun=body?.dry_run===true;
    const keys=JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS")||"{}");
    const serviceKey=keys.default||Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
    if(!serviceKey)throw new Error("missing_service_key");
    const testers:Tester[]=await rows("testers?select=tester_code,telegram_chat_id,locations,voivodeships,max_price,min_area,max_area,min_rooms,max_rooms,max_price_m2,min_market_discount_pct,flip_analysis_enabled,exclusions&active=eq.true&telegram_chat_id=not.is.null",serviceKey);
    if(mode==="summary"){
      const now=new Date(),localDate=warsawDate(now),localHour=warsawHour(now);
      if(localHour!==20&&!dryRun)return json({ok:true,mode,skipped:"outside_20_warsaw",local_hour:localHour});
      const since=new Date(now.getTime()-26*60*60*1000).toISOString();
      const recent=await rows("deliveries?select=tester_code,source,source_offer_id,sent_at&sent_at=gte."+encodeURIComponent(since),serviceKey);
      const sent:string[]=[];
      const skipped:string[]=[];
      for(const tester of testers){
        const source="summary:daily";
        if(await alreadyDelivered(serviceKey,tester.tester_code,source,localDate)){skipped.push(tester.tester_code);continue;}
        const count=recent.filter((d:any)=>d.tester_code===tester.tester_code&&warsawDate(new Date(d.sent_at))===localDate&&!String(d.source).startsWith("test:")&&d.source!==source).length;
        const text=count===0
          ?"📊 PODSUMOWANIE DNIA — RADAR OKAZJI\n\nDzisiaj 0 ofert spełniających kryteria dobrego flipa.\n\nSystem sprawdza wszystkie podłączone portale co godzinę i będzie szukał dalej."
          :"📊 PODSUMOWANIE DNIA — RADAR OKAZJI\n\nDzisiaj znaleziono i wysłano "+count+" "+(count===1?"ofertę":count<5?"oferty":"ofert")+" spełniających kryteria dobrego flipa.";
        if(dryRun){sent.push(tester.tester_code+":"+count);continue;}
        const message=await telegram(botToken,"sendMessage",{chat_id:tester.telegram_chat_id,text});
        await recordDelivery(serviceKey,tester.tester_code,source,localDate,message.message_id);
        sent.push(tester.tester_code+":"+count);
      }
      return json({ok:true,mode,local_date:localDate,sent_count:sent.length,sent,skipped,dry_run:dryRun});
    }
    const rpc=await db("rpc/recompute_flip_analysis",serviceKey,{method:"POST",body:"{}"});
    if(!rpc.ok)throw new Error("analysis_"+rpc.status);
    const since=new Date(Date.now()-2*60*60*1000).toISOString();
    const select="source,source_offer_id,title,url,city,voivodeship,price,area,rooms,price_m2,floor_text,description,market_price_m2,market_discount_pct,suggested_purchase_price,renovation_cost_low,renovation_cost_high,suggested_sale_price,estimated_profit_low,estimated_profit_high,analysis_confidence,last_seen_at";
    const candidates:Candidate[]=await rows("source_candidates?select="+select+"&flip_match=eq.true&last_seen_at=gte."+encodeURIComponent(since)+"&order=last_seen_at.desc&limit=200",serviceKey);
    const sent:string[]=[];
    const errors:string[]=[];
    let matched=0;
    for(const candidate of candidates){
      for(const tester of testers){
        if(!matches(tester,candidate))continue;
        matched++;
        if(await alreadyDelivered(serviceKey,tester.tester_code,candidate.source,candidate.source_offer_id))continue;
        if(dryRun){sent.push(tester.tester_code+":"+candidate.source+":"+candidate.source_offer_id);continue;}
        try{
          const message=await telegram(botToken,"sendMessage",{chat_id:tester.telegram_chat_id,text:offerMessage(candidate,Boolean(tester.flip_analysis_enabled)),disable_web_page_preview:false});
          await recordDelivery(serviceKey,tester.tester_code,candidate.source,candidate.source_offer_id,message.message_id);
          sent.push(tester.tester_code+":"+candidate.source+":"+candidate.source_offer_id);
        }catch(error){errors.push((tester.tester_code+":"+candidate.source_offer_id+":"+String(error)).slice(0,500));}
      }
    }
    return json({ok:errors.length===0,mode,candidates:candidates.length,matched,sent_count:sent.length,sent,errors,dry_run:dryRun});
  }catch(error){
    console.error(error);
    return json({error:String(error)},500);
  }
});