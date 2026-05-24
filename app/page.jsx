'use client';

import React, { useMemo, useState } from 'react';
import { Search, Package, Boxes, Bot, RefreshCw, ShoppingCart, AlertTriangle, Plus, Wand2, ImagePlus, BarChart3, Megaphone, Upload, Save, Trash2, CheckCircle2 } from 'lucide-react';

const initialUnits = [
  { id: 'BLK-M', baseCode: 'MEL-SHORTS', color: '黒', size: 'M', category: 'ショーツ', imageUrl: 'https://placehold.co/240x240?text=BLK-M', qty: 126, safety: 20, cost: 320 },
  { id: 'WHT-M', baseCode: 'MEL-SHORTS', color: '白', size: 'M', category: 'ショーツ', imageUrl: 'https://placehold.co/240x240?text=WHT-M', qty: 88, safety: 15, cost: 320 },
  { id: 'GRY-M', baseCode: 'MEL-SHORTS', color: 'グレー', size: 'M', category: 'ショーツ', imageUrl: 'https://placehold.co/240x240?text=GRY-M', qty: 54, safety: 12, cost: 320 },
  { id: 'BLK-L', baseCode: 'MEL-SHORTS', color: '黒', size: 'L', category: 'ショーツ', imageUrl: 'https://placehold.co/240x240?text=BLK-L', qty: 72, safety: 12, cost: 335 },
  { id: 'WHT-L', baseCode: 'MEL-SHORTS', color: '白', size: 'L', category: 'ショーツ', imageUrl: 'https://placehold.co/240x240?text=WHT-L', qty: 45, safety: 10, cost: 335 },
];

const initialSkus = [
  { id: 'AMZ-PARENT-001-BLK-MIX-5', mall: 'Amazon', parent: 'AMZ-PARENT-001', name: '5枚セット 黒白MIX M', stock: 20, parts: [{ unitId: 'BLK-M', qty: 2 }, { unitId: 'WHT-M', qty: 3 }], sales30d: 68, adCost30d: 18400, revenue30d: 176800, price: 2600 },
  { id: 'AMZ-PARENT-001-DARK-5', mall: 'Amazon', parent: 'AMZ-PARENT-001', name: '5枚セット ダーク M', stock: 18, parts: [{ unitId: 'BLK-M', qty: 1 }, { unitId: 'GRY-M', qty: 4 }], sales30d: 42, adCost30d: 9800, revenue30d: 109200, price: 2600 },
  { id: 'RKT-SET-7-MIX-M', mall: '楽天', parent: 'RKT-PARENT-901', name: '7枚セット MIX M', stock: 12, parts: [{ unitId: 'BLK-M', qty: 2 }, { unitId: 'WHT-M', qty: 2 }, { unitId: 'GRY-M', qty: 3 }], sales30d: 36, adCost30d: 12600, revenue30d: 140400, price: 3900 },
  { id: 'RKT-SINGLE-BLK-L', mall: '楽天', parent: 'RKT-PARENT-902', name: '単品 黒 L', stock: 32, parts: [{ unitId: 'BLK-L', qty: 1 }], sales30d: 28, adCost30d: 4200, revenue30d: 36400, price: 1300 },
  { id: 'AMZ-SINGLE-WHT-L', mall: 'Amazon', parent: 'AMZ-PARENT-002', name: '単品 白 L', stock: 18, parts: [{ unitId: 'WHT-L', qty: 1 }], sales30d: 16, adCost30d: 3100, revenue30d: 20800, price: 1300 },
];

const initialOrders = [
  { id: 'AMZ-ORDER-1001', mall: 'Amazon', skuId: 'AMZ-PARENT-001-BLK-MIX-5', qty: 2, date: '2026-05-24 10:42', status: '反映済み' },
  { id: 'RKT-ORDER-1002', mall: '楽天', skuId: 'RKT-SET-7-MIX-M', qty: 1, date: '2026-05-24 09:18', status: '反映済み' },
];

const tabs = [
  { key: 'home', label: 'ホーム', icon: BarChart3 },
  { key: 'units', label: '単品', icon: Package },
  { key: 'skus', label: '販売SKU', icon: Boxes },
  { key: 'orders', label: '注文', icon: ShoppingCart },
  { key: 'ai', label: 'AI', icon: Bot },
];

function unitName(unit) {
  if (!unit) return '未登録';
  return `${unit.color}${unit.size ? ' ' + unit.size : ''}`;
}

function unitMap(units) {
  return Object.fromEntries(units.map((unit) => [unit.id, unit]));
}

function skuAvailable(sku, units) {
  const map = unitMap(units);
  if (!sku.parts.length) return 0;
  return Math.min(...sku.parts.map((part) => {
    const unit = map[part.unitId];
    if (!unit) return 0;
    return Math.floor(Math.max(unit.qty - unit.safety, 0) / Math.max(part.qty, 1));
  }));
}

function skuCost(sku, units) {
  const map = unitMap(units);
  return sku.parts.reduce((sum, part) => sum + (map[part.unitId]?.cost || 0) * part.qty, 0);
}

function enrich(skus, units) {
  const totalSales = skus.reduce((sum, sku) => sum + Number(sku.sales30d || 0), 0) || 1;
  return skus.map((sku) => {
    const available = skuAvailable(sku, units);
    const rate = Number(sku.sales30d || 0) / totalSales;
    const recommended = Math.max(0, Math.floor(available * rate));
    const cost = skuCost(sku, units);
    const profit = sku.revenue30d - sku.sales30d * cost - sku.adCost30d;
    const acos = sku.revenue30d ? sku.adCost30d / sku.revenue30d : 0;
    return { ...sku, available, recommended, cost, profit, acos, rate };
  });
}

function today() {
  return new Date().toLocaleString('ja-JP', { hour12: false });
}

export default function MellowInventoryApp() {
  const [activeTab, setActiveTab] = useState('home');
  const [units, setUnits] = useState(initialUnits);
  const [skus, setSkus] = useState(initialSkus);
  const [orders, setOrders] = useState(initialOrders);
  const [unitQuery, setUnitQuery] = useState('');
  const [skuQuery, setSkuQuery] = useState('');
  const [selectedUnitId, setSelectedUnitId] = useState(initialUnits[0].id);
  const [selectedSkuId, setSelectedSkuId] = useState(initialSkus[0].id);
  const [aiInput, setAiInput] = useState('今月の売上、広告費、粗利をまとめて。在庫が少ない単品と、各SKUの推奨在庫数も出して');
  const [aiAnswer, setAiAnswer] = useState('聞きたいことを入力して実行してください。');
  const [log, setLog] = useState(['商品・注文・在庫を同期しました', '単品在庫から販売SKUの販売可能数を計算しました']);

  const map = useMemo(() => unitMap(units), [units]);
  const richSkus = useMemo(() => enrich(skus, units), [skus, units]);
  const selectedUnit = units.find((unit) => unit.id === selectedUnitId) || units[0];
  const selectedSku = richSkus.find((sku) => sku.id === selectedSkuId) || richSkus[0];
  const filteredUnits = units.filter((unit) => `${unit.id} ${unit.baseCode} ${unit.color} ${unit.size} ${unit.category}`.toLowerCase().includes(unitQuery.toLowerCase()));
  const filteredSkus = richSkus.filter((sku) => `${sku.id} ${sku.parent} ${sku.name} ${sku.mall}`.toLowerCase().includes(skuQuery.toLowerCase()));
  const totals = useMemo(() => {
    const revenue = richSkus.reduce((sum, sku) => sum + sku.revenue30d, 0);
    const adCost = richSkus.reduce((sum, sku) => sum + sku.adCost30d, 0);
    const profit = richSkus.reduce((sum, sku) => sum + sku.profit, 0);
    const alert = units.filter((unit) => unit.qty <= unit.safety).length;
    return { revenue, adCost, profit, acos: revenue ? adCost / revenue : 0, alert };
  }, [richSkus, units]);

  const addLog = (text) => setLog((prev) => [`${today()} ${text}`, ...prev]);
  const sync = () => addLog('Amazon・楽天の最新データを取得しました');
  const publish = () => addLog('販売SKUの在庫数をAmazon・楽天へ反映しました');

  const addUnit = () => {
    const id = `UNIT-${String(units.length + 1).padStart(3, '0')}`;
    const unit = { id, baseCode: 'MEL-NEW', color: '新色', size: 'M', category: '未分類', imageUrl: `https://placehold.co/240x240?text=${id}`, qty: 0, safety: 0, cost: 0 };
    setUnits((prev) => [...prev, unit]);
    setSelectedUnitId(id);
    addLog(`${id}を追加しました`);
  };
  const updateUnit = (id, patch) => setUnits((prev) => prev.map((unit) => (unit.id === id ? { ...unit, ...patch } : unit)));
  const deleteUnit = (id) => {
    if (skus.some((sku) => sku.parts.some((part) => part.unitId === id))) {
      addLog(`${id}は販売SKUで使用中のため削除できません`);
      return;
    }
    setUnits((prev) => prev.filter((unit) => unit.id !== id));
    setSelectedUnitId(units[0]?.id || '');
    addLog(`${id}を削除しました`);
  };

  const addSku = () => {
    const id = `SKU-${String(skus.length + 1).padStart(3, '0')}`;
    const sku = { id, mall: 'Amazon', parent: '', name: '新規SKU', stock: 0, parts: units[0] ? [{ unitId: units[0].id, qty: 1 }] : [], sales30d: 0, adCost30d: 0, revenue30d: 0, price: 0 };
    setSkus((prev) => [...prev, sku]);
    setSelectedSkuId(id);
    addLog(`${id}を追加しました`);
  };
  const updateSku = (id, patch) => setSkus((prev) => prev.map((sku) => (sku.id === id ? { ...sku, ...patch } : sku)));
  const addPart = (skuId) => units[0] && setSkus((prev) => prev.map((sku) => (sku.id === skuId ? { ...sku, parts: [...sku.parts, { unitId: units[0].id, qty: 1 }] } : sku)));
  const updatePart = (skuId, index, patch) => setSkus((prev) => prev.map((sku) => (sku.id === skuId ? { ...sku, parts: sku.parts.map((part, i) => (i === index ? { ...part, ...patch } : part)) } : sku)));
  const deletePart = (skuId, index) => setSkus((prev) => prev.map((sku) => (sku.id === skuId ? { ...sku, parts: sku.parts.filter((_, i) => i !== index) } : sku)));

  const addOrder = ({ mall, skuId, qty }) => {
    const sku = skus.find((item) => item.id === skuId);
    if (!sku) return;
    const id = `${mall === 'Amazon' ? 'AMZ' : 'RKT'}-ORDER-${1000 + orders.length + 1}`;
    setUnits((prev) => prev.map((unit) => {
      const part = sku.parts.find((item) => item.unitId === unit.id);
      return part ? { ...unit, qty: Math.max(0, unit.qty - part.qty * qty) } : unit;
    }));
    setOrders((prev) => [{ id, mall, skuId, qty, date: today(), status: '反映済み' }, ...prev]);
    addLog(`${mall}の注文 ${id} を在庫に反映しました`);
  };

  const runAi = () => {
    const best = [...richSkus].sort((a, b) => b.profit - a.profit)[0];
    const alerts = units.filter((unit) => unit.qty <= unit.safety + 10);
    setAiAnswer([
      `売上 ¥${totals.revenue.toLocaleString()} / 広告費 ¥${totals.adCost.toLocaleString()} / ACOS ${(totals.acos * 100).toFixed(1)}% / 粗利 ¥${totals.profit.toLocaleString()}`,
      best ? `粗利が一番大きいSKUは「${best.name}」です。` : 'SKUがありません。',
      alerts.length ? `在庫が少ない単品: ${alerts.map(unitName).join('、')}` : '在庫が少ない単品はありません。',
      '販売SKU一覧の「推奨」列に、直近30日販売数をもとにした在庫数を出しています。',
    ].join('\n\n'));
    addLog('AIで集計しました');
  };
  const applyRecommended = () => {
    setSkus((prev) => enrich(prev, units).map((sku) => ({ ...sku, stock: sku.recommended })));
    addLog('推奨在庫数を販売SKUに反映しました');
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="flex min-h-screen">
        <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white p-5 lg:flex">
          <div className="mb-8"><div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">mellow</div><div className="mt-1 text-2xl font-bold">在庫管理</div></div>
          <nav className="space-y-2">{tabs.map((tab) => { const Icon = tab.icon; return <button key={tab.key} onClick={() => setActiveTab(tab.key)} className={`flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left ${activeTab === tab.key ? 'bg-slate-900 text-white' : 'hover:bg-slate-100'}`}><Icon size={18}/><span className="font-medium">{tab.label}</span></button>; })}</nav>
        </aside>
        <main className="flex-1 p-4 md:p-8">
          <header className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div><div className="text-sm text-slate-500">Amazon・楽天</div><h1 className="text-3xl font-bold tracking-tight">mellow 在庫管理</h1></div>
            <div className="flex flex-wrap gap-2"><button onClick={sync} className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm"><RefreshCw size={18}/>同期</button><button onClick={publish} className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-4 py-3 text-white shadow-sm"><Upload size={18}/>在庫反映</button></div>
          </header>
          <div className="mb-6 flex gap-2 overflow-auto lg:hidden">{tabs.map((tab) => <button key={tab.key} onClick={() => setActiveTab(tab.key)} className={`whitespace-nowrap rounded-full px-4 py-2 text-sm ${activeTab === tab.key ? 'bg-slate-900 text-white' : 'border border-slate-200 bg-white'}`}>{tab.label}</button>)}</div>
          {activeTab === 'home' && <Home totals={totals} units={units} skus={richSkus} orders={orders} setActiveTab={setActiveTab}/>} 
          {activeTab === 'units' && <Units units={filteredUnits} allUnits={units} selectedUnit={selectedUnit} query={unitQuery} setQuery={setUnitQuery} setSelectedUnitId={setSelectedUnitId} addUnit={addUnit} updateUnit={updateUnit} deleteUnit={deleteUnit}/>} 
          {activeTab === 'skus' && <Skus skus={filteredSkus} units={units} map={map} selectedSku={selectedSku} query={skuQuery} setQuery={setSkuQuery} setSelectedSkuId={setSelectedSkuId} addSku={addSku} updateSku={updateSku} addPart={addPart} updatePart={updatePart} deletePart={deletePart} applyRecommended={applyRecommended}/>} 
          {activeTab === 'orders' && <Orders orders={orders} skus={richSkus} addOrder={addOrder}/>} 
          {activeTab === 'ai' && <Ai input={aiInput} setInput={setAiInput} answer={aiAnswer} runAi={runAi} applyRecommended={applyRecommended} totals={totals}/>} 
          <Card className="mt-6"><div className="mb-3 flex items-center justify-between"><h2 className="text-lg font-semibold">履歴</h2><span className="text-xs text-slate-500">最新順</span></div><div className="space-y-2">{log.slice(0, 5).map((item, index) => <div key={`${item}-${index}`} className="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">{item}</div>)}</div></Card>
        </main>
      </div>
    </div>
  );
}

function Home({ totals, units, skus, orders, setActiveTab }) {
  const topSkus = [...skus].sort((a, b) => b.revenue30d - a.revenue30d).slice(0, 4);
  const alerts = units.filter((unit) => unit.qty <= unit.safety + 10);
  return <div className="space-y-6"><div className="grid grid-cols-1 gap-4 md:grid-cols-5"><Metric icon={<Package/>} label="単品" value={`${units.length}件`}/><Metric icon={<Boxes/>} label="販売SKU" value={`${skus.length}件`}/><Metric icon={<ShoppingCart/>} label="注文" value={`${orders.length}件`}/><Metric icon={<BarChart3/>} label="売上" value={`¥${totals.revenue.toLocaleString()}`}/><Metric icon={<Megaphone/>} label="ACOS" value={`${(totals.acos * 100).toFixed(1)}%`}/></div><div className="grid grid-cols-1 gap-6 xl:grid-cols-3"><Card className="xl:col-span-2"><div className="mb-4 flex items-center justify-between"><h2 className="text-xl font-semibold">売れているSKU</h2><button onClick={() => setActiveTab('skus')} className="rounded-xl border px-3 py-2 text-sm">販売SKUを見る</button></div><div className="space-y-3">{topSkus.map((sku) => <div key={sku.id} className="rounded-2xl border border-slate-100 p-4"><div className="flex items-center justify-between gap-3"><div><div className="font-semibold">{sku.name}</div><div className="mt-1 text-xs text-slate-500">{sku.mall} / {sku.id}</div></div><div className="text-right"><div className="font-bold">¥{sku.revenue30d.toLocaleString()}</div><div className="text-xs text-slate-500">粗利 ¥{sku.profit.toLocaleString()}</div></div></div></div>)}</div></Card><Card><div className="mb-4 flex items-center gap-2"><AlertTriangle size={20}/><h2 className="text-xl font-semibold">在庫アラート</h2></div>{alerts.length ? <div className="space-y-3">{alerts.map((unit) => <div key={unit.id} className="rounded-xl bg-amber-50 p-3"><div className="font-semibold">{unitName(unit)}</div><div className="text-sm text-slate-600">現在 {unit.qty} / 最低 {unit.safety}</div></div>)}</div> : <div className="rounded-xl bg-emerald-50 p-4 text-sm">不足しそうな単品はありません。</div>}</Card></div></div>;
}

function Units({ units, allUnits, selectedUnit, query, setQuery, setSelectedUnitId, addUnit, updateUnit, deleteUnit }) {
  return <div className="grid grid-cols-1 gap-6 xl:grid-cols-3"><Card className="xl:col-span-2"><div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between"><h2 className="text-xl font-semibold">単品</h2><div className="flex gap-2"><SearchBox value={query} onChange={setQuery} placeholder="ID・色・サイズで検索"/><button onClick={addUnit} className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-white"><Plus size={16}/>追加</button></div></div><div className="grid grid-cols-1 gap-3 md:grid-cols-2">{units.map((unit) => <button key={unit.id} onClick={() => setSelectedUnitId(unit.id)} className={`rounded-2xl border p-4 text-left hover:bg-slate-50 ${selectedUnit?.id === unit.id ? 'border-slate-900' : 'border-slate-100'}`}><div className="flex gap-4"><img src={unit.imageUrl} alt="" className="h-20 w-20 rounded-2xl bg-slate-100 object-cover"/><div className="min-w-0 flex-1"><div className="font-semibold">{unitName(unit)}</div><div className="mt-1 truncate text-xs font-mono text-slate-500">{unit.id}</div><div className="mt-2 text-sm text-slate-600">在庫 {unit.qty} / 最低 {unit.safety} / 原価 ¥{Number(unit.cost).toLocaleString()}</div><div className="mt-1 text-xs text-slate-400">{unit.baseCode} / {unit.category}</div></div></div></button>)}</div></Card><Card><div className="mb-4 flex items-center justify-between"><h2 className="text-xl font-semibold">編集</h2><button onClick={() => deleteUnit(selectedUnit.id)} className="rounded-xl border border-red-200 p-2 text-red-600"><Trash2 size={16}/></button></div>{selectedUnit && <div className="space-y-3"><div><img src={selectedUnit.imageUrl} alt="" className="mb-3 h-48 w-full rounded-2xl bg-slate-100 object-cover"/><input type="file" accept="image/*" className="hidden" id="unit-image" onChange={(event) => { const file = event.target.files?.[0]; if (file) updateUnit(selectedUnit.id, { imageUrl: URL.createObjectURL(file) }); }}/><label htmlFor="unit-image" className="inline-flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 text-sm"><ImagePlus size={16}/>画像を選択</label></div><Field label="単品ID" value={selectedUnit.id} onChange={(value) => updateUnit(selectedUnit.id, { id: value })}/><Field label="品番" value={selectedUnit.baseCode} onChange={(value) => updateUnit(selectedUnit.id, { baseCode: value })}/><div className="grid grid-cols-2 gap-3"><Field label="色" value={selectedUnit.color} onChange={(value) => updateUnit(selectedUnit.id, { color: value })}/><Field label="サイズ" value={selectedUnit.size} onChange={(value) => updateUnit(selectedUnit.id, { size: value })}/></div><Field label="カテゴリ" value={selectedUnit.category} onChange={(value) => updateUnit(selectedUnit.id, { category: value })}/><div className="grid grid-cols-3 gap-3"><Field type="number" label="在庫" value={selectedUnit.qty} onChange={(value) => updateUnit(selectedUnit.id, { qty: Number(value) })}/><Field type="number" label="最低" value={selectedUnit.safety} onChange={(value) => updateUnit(selectedUnit.id, { safety: Number(value) })}/><Field type="number" label="原価" value={selectedUnit.cost} onChange={(value) => updateUnit(selectedUnit.id, { cost: Number(value) })}/></div><div className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">登録数 {allUnits.length}件</div></div>}</Card></div>;
}

function Skus({ skus, units, map, selectedSku, query, setQuery, setSelectedSkuId, addSku, updateSku, addPart, updatePart, deletePart, applyRecommended }) {
  return <div className="grid grid-cols-1 gap-6 xl:grid-cols-3"><Card className="xl:col-span-2"><div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between"><h2 className="text-xl font-semibold">販売SKU</h2><div className="flex gap-2"><SearchBox value={query} onChange={setQuery} placeholder="SKU・商品名で検索"/><button onClick={applyRecommended} className="rounded-xl border px-4 py-2">推奨を反映</button><button onClick={addSku} className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-white"><Plus size={16}/>追加</button></div></div><div className="overflow-auto"><table className="w-full text-sm"><thead className="border-b text-left text-slate-500"><tr><th className="py-3">モール</th><th>SKU</th><th>商品名</th><th>中身</th><th className="text-right">現在</th><th className="text-right">販売可</th><th className="text-right">推奨</th></tr></thead><tbody>{skus.map((sku) => <tr key={sku.id} onClick={() => setSelectedSkuId(sku.id)} className="cursor-pointer border-b hover:bg-slate-50"><td className="py-3"><MallBadge mall={sku.mall}/></td><td className="max-w-44 truncate font-mono text-xs">{sku.id}</td><td>{sku.name}</td><td className="text-xs text-slate-600">{sku.parts.map((part) => `${unitName(map[part.unitId])}×${part.qty}`).join(' / ')}</td><td className="text-right">{sku.stock}</td><td className="text-right">{sku.available}</td><td className="text-right font-semibold">{sku.recommended}</td></tr>)}</tbody></table></div></Card><Card><h2 className="mb-4 text-xl font-semibold">編集</h2>{selectedSku && <div className="space-y-3"><Field label="SKU" value={selectedSku.id} onChange={(value) => updateSku(selectedSku.id, { id: value })}/><Field label="親SKU" value={selectedSku.parent} onChange={(value) => updateSku(selectedSku.id, { parent: value })}/><label className="block text-sm"><div className="mb-1 text-slate-500">モール</div><select className="w-full rounded-xl border border-slate-200 px-3 py-2" value={selectedSku.mall} onChange={(event) => updateSku(selectedSku.id, { mall: event.target.value })}><option>Amazon</option><option>楽天</option></select></label><Field label="商品名" value={selectedSku.name} onChange={(value) => updateSku(selectedSku.id, { name: value })}/><div className="grid grid-cols-3 gap-3"><Field type="number" label="価格" value={selectedSku.price} onChange={(value) => updateSku(selectedSku.id, { price: Number(value) })}/><Field type="number" label="在庫" value={selectedSku.stock} onChange={(value) => updateSku(selectedSku.id, { stock: Number(value) })}/><Field type="number" label="30日販売" value={selectedSku.sales30d} onChange={(value) => updateSku(selectedSku.id, { sales30d: Number(value) })}/></div><div className="grid grid-cols-2 gap-3"><Field type="number" label="30日売上" value={selectedSku.revenue30d} onChange={(value) => updateSku(selectedSku.id, { revenue30d: Number(value) })}/><Field type="number" label="30日広告費" value={selectedSku.adCost30d} onChange={(value) => updateSku(selectedSku.id, { adCost30d: Number(value) })}/></div><div className="rounded-2xl border border-slate-100 p-3"><div className="mb-3 flex items-center justify-between"><div className="font-semibold">中身</div><button onClick={() => addPart(selectedSku.id)} className="rounded-xl border px-3 py-1 text-sm">追加</button></div><div className="space-y-2">{selectedSku.parts.map((part, index) => <div key={index} className="grid grid-cols-[1fr_80px_36px] gap-2"><select className="rounded-xl border border-slate-200 px-2 py-2 text-sm" value={part.unitId} onChange={(event) => updatePart(selectedSku.id, index, { unitId: event.target.value })}>{units.map((unit) => <option key={unit.id} value={unit.id}>{unit.id} / {unitName(unit)}</option>)}</select><input type="number" className="rounded-xl border border-slate-200 px-2 py-2 text-sm" value={part.qty} onChange={(event) => updatePart(selectedSku.id, index, { qty: Number(event.target.value) })}/><button onClick={() => deletePart(selectedSku.id, index)} className="rounded-xl border text-red-500">×</button></div>)}</div></div><div className="rounded-xl bg-slate-50 p-3 text-sm"><div>販売可能: <b>{selectedSku.available}</b></div><div>推奨在庫: <b>{selectedSku.recommended}</b></div><div>ACOS: <b>{(selectedSku.acos * 100).toFixed(1)}%</b></div><div>原価: <b>¥{selectedSku.cost.toLocaleString()}</b></div></div></div>}</Card></div>;
}

function Orders({ orders, skus, addOrder }) {
  const [mall, setMall] = useState('Amazon');
  const [skuId, setSkuId] = useState(skus[0]?.id || '');
  const [qty, setQty] = useState(1);
  return <div className="grid grid-cols-1 gap-6 xl:grid-cols-3"><Card><h2 className="mb-4 text-xl font-semibold">注文追加</h2><div className="space-y-3"><label className="block text-sm"><div className="mb-1 text-slate-500">モール</div><select className="w-full rounded-xl border px-3 py-2" value={mall} onChange={(event) => setMall(event.target.value)}><option>Amazon</option><option>楽天</option></select></label><label className="block text-sm"><div className="mb-1 text-slate-500">SKU</div><select className="w-full rounded-xl border px-3 py-2" value={skuId} onChange={(event) => setSkuId(event.target.value)}>{skus.map((sku) => <option key={sku.id} value={sku.id}>{sku.mall} / {sku.name}</option>)}</select></label><Field type="number" label="数量" value={qty} onChange={(value) => setQty(Number(value))}/><button onClick={() => addOrder({ mall, skuId, qty })} className="w-full rounded-2xl bg-slate-900 px-4 py-3 text-white">在庫に反映</button></div></Card><Card className="xl:col-span-2"><h2 className="mb-4 text-xl font-semibold">注文一覧</h2><div className="overflow-auto"><table className="w-full text-sm"><thead className="border-b text-left text-slate-500"><tr><th className="py-3">日時</th><th>注文ID</th><th>モール</th><th>SKU</th><th className="text-right">数量</th><th>状態</th></tr></thead><tbody>{orders.map((order) => <tr key={order.id} className="border-b"><td className="py-3">{order.date}</td><td className="font-mono text-xs">{order.id}</td><td><MallBadge mall={order.mall}/></td><td className="max-w-64 truncate">{skus.find((sku) => sku.id === order.skuId)?.name || order.skuId}</td><td className="text-right">{order.qty}</td><td><span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-xs text-emerald-700"><CheckCircle2 size={12}/>{order.status}</span></td></tr>)}</tbody></table></div></Card></div>;
}

function Ai({ input, setInput, answer, runAi, applyRecommended, totals }) {
  return <div className="grid grid-cols-1 gap-6 xl:grid-cols-3"><Card className="xl:col-span-2"><div className="mb-4 flex items-center gap-2"><Bot/><h2 className="text-xl font-semibold">AI</h2></div><textarea className="min-h-36 w-full rounded-2xl border border-slate-200 p-4" value={input} onChange={(event) => setInput(event.target.value)}/><div className="mt-3 flex flex-wrap gap-2"><button onClick={runAi} className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-4 py-3 text-white"><Wand2 size={18}/>実行</button><button onClick={applyRecommended} className="inline-flex items-center gap-2 rounded-2xl border px-4 py-3"><Save size={18}/>推奨在庫を反映</button></div><div className="mt-5 whitespace-pre-line rounded-2xl bg-slate-50 p-5 text-sm leading-6 text-slate-700">{answer}</div></Card><Card><h2 className="mb-4 text-xl font-semibold">集計</h2><div className="space-y-3 text-sm"><Row label="売上" value={`¥${totals.revenue.toLocaleString()}`}/><Row label="広告費" value={`¥${totals.adCost.toLocaleString()}`}/><Row label="ACOS" value={`${(totals.acos * 100).toFixed(1)}%`}/><Row label="粗利" value={`¥${totals.profit.toLocaleString()}`}/></div></Card></div>;
}

function SearchBox({ value, onChange, placeholder }) { return <div className="relative"><Search className="absolute left-3 top-2.5 text-slate-400" size={17}/><input className="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 md:w-72" value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder}/></div>; }
function Field({ label, value, onChange, type = 'text' }) { return <label className="block text-sm"><div className="mb-1 text-slate-500">{label}</div><input type={type} className="w-full rounded-xl border border-slate-200 px-3 py-2" value={value ?? ''} onChange={(event) => onChange(event.target.value)}/></label>; }
function Row({ label, value }) { return <div className="flex items-center justify-between rounded-xl bg-slate-50 px-4 py-3"><span className="text-slate-500">{label}</span><span className="font-semibold">{value}</span></div>; }
function Card({ children, className = '' }) { return <section className={`rounded-3xl border border-slate-200 bg-white p-5 shadow-sm ${className}`}>{children}</section>; }
function Metric({ icon, label, value }) { return <Card><div className="mb-3 text-slate-500">{icon}</div><div className="text-sm text-slate-500">{label}</div><div className="mt-1 text-2xl font-bold">{value}</div></Card>; }
function MallBadge({ mall }) { return <span className={`rounded-full px-2 py-1 text-xs ${mall === 'Amazon' ? 'bg-orange-50 text-orange-700' : 'bg-red-50 text-red-700'}`}>{mall}</span>; }
