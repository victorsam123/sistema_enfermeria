const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { employeeEntryYear } = require('../app/static/js/employees.js');

function setup() {
  const events = {}, nodes = {year:{value:''}, tenure:{textContent:''}, reference:{textContent:''}};
  const date = {value:'',addEventListener:(event,fn)=>events[event]=fn};
  const csrf = {value:'test-csrf'};
  const form = {dataset:{previewUrl:'/funcionarios/9/vinculos/calcular-antiguedad'},
    elements:{namedItem:name=>name==='fecha_ingreso'?date:csrf},querySelector:()=>nodes.reference};
  let timer, request;
  const pending=[];
  const context = {employeeEntryYear,
    document:{querySelectorAll:()=>[form],getElementById:id=>id==='employment-year'?nodes.year:nodes.tenure},
    setTimeout:fn=>{timer=fn;return 1;},clearTimeout:()=>{timer=null;},
    fetch:(url,options)=>{request={url,options};return new Promise(resolve=>pending.push(resolve));}};
  vm.runInNewContext(fs.readFileSync('app/static/js/employment_links.js','utf8'),context);
  return {nodes,pending,get request(){return request;},change:value=>{date.value=value;events.input();},run:()=>timer()};
}
const answer=(data,ok=true)=>({ok,json:async()=>data});
test('La vista previa usa el calendario del servidor y POST con CSRF',async()=>{
  const h=setup();h.change('15/06/2020');const done=h.run();
  assert.equal(h.request.options.method,'POST');assert.equal(h.request.options.headers['X-CSRFToken'],'test-csrf');
  assert.deepEqual(JSON.parse(h.request.options.body),{fecha_ingreso:'15/06/2020'});
  h.pending[0](answer({anio_ingreso:2020,anios:6,meses:4,dias:7,fecha_consulta:'22/10/2026'}));await done;
  assert.equal(h.nodes.tenure.textContent,'6 años, 4 meses y 7 días');assert.equal(h.nodes.year.value,2020);
  assert.match(h.nodes.reference.textContent,/America\/Asuncion/);
});
test('Una respuesta atrasada no sobrescribe una fecha elegida después',async()=>{
  const h=setup();h.change('15/06/2020');const first=h.run();h.change('01/02/2024');const second=h.run();
  h.pending[1](answer({anio_ingreso:2024,anios:2,meses:8,dias:21,fecha_consulta:'22/10/2026'}));await second;
  h.pending[0](answer({anio_ingreso:2020,anios:6,meses:4,dias:7,fecha_consulta:'22/10/2026'}));await first;
  assert.equal(h.nodes.tenure.textContent,'2 años, 8 meses y 21 días');assert.equal(h.nodes.year.value,2024);
});
test('No completa años aislados ni fechas inválidas y maneja rechazo del servidor',async()=>{
  const h=setup();h.change('2020');await h.run();assert.equal(h.request,undefined);
  h.change('31/02/2020');await h.run();assert.equal(h.request,undefined);
  h.change('01/01/2999');const pending=h.run();h.pending[0](answer({},false));await pending;
  assert.match(h.nodes.tenure.textContent,/Revisa la fecha/);
});
