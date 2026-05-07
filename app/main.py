import json, re, uuid
from pathlib import Path
from typing import Any
import requests
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
BASE=Path('/opt/rag'); DATA=BASE/'data'; DATA.mkdir(exist_ok=True)
CFG=BASE/'config'/'kizuna.json'; CFG.parent.mkdir(exist_ok=True)
COLLECTION='rag_chunks'; QDRANT='http://127.0.0.1:6333'
app=FastAPI(title='Lightweight RAG PoC')
templates=Jinja2Templates('/opt/rag/app/templates')
def load_cfg():
    return json.loads(CFG.read_text()) if CFG.exists() else {'base_url':'','api_key':'','ocr_path':'','embed_path':'','auth_header':'Authorization','auth_prefix':'Bearer','ocr_method':'GET','embed_method':'POST'}
def save_cfg(d): CFG.write_text(json.dumps(d, indent=2, ensure_ascii=False))
def headers(c):
    h={'Accept':'application/json'}
    if c.get('api_key'):
        h[c.get('auth_header') or 'Authorization']=((c.get('auth_prefix','')+' '+c['api_key']).strip())
    return h
def clean_md(s): return re.sub(r'\n{3,}','\n\n',re.sub(r'[ \t]+\n','\n',s or '')).strip()
def chunks(text, size=800, overlap=150):
    text=clean_md(text); out=[]; i=0
    while i < len(text): out.append(text[i:i+size]); i += max(1,size-overlap)
    return [x for x in out if x.strip()]
def req_json(method,url,headers,json_body=None,params=None):
    r=requests.request(method,url,headers=headers,json=json_body,params=params,timeout=60)
    try: body=r.json()
    except Exception: body={'raw_text':r.text}
    if r.status_code>=400: raise RuntimeError(json.dumps({'status':r.status_code,'body':body},ensure_ascii=False,indent=2))
    return body
def extract_markdown(body:Any):
    if isinstance(body,str): return body
    if isinstance(body,dict):
        for k in ['markdown','content','text','result']:
            v=body.get(k)
            if isinstance(v,str): return v
            if isinstance(v,dict):
                for kk in ['markdown','content','text']:
                    if isinstance(v.get(kk),str): return v[kk]
    raise RuntimeError('Cannot find markdown in response. Raw: '+json.dumps(body,ensure_ascii=False)[:2000])
def extract_embedding(body:Any):
    if isinstance(body,dict):
        paths=[('embedding',),('vector',),('data',0,'embedding'),('result','embedding')]
        for path in paths:
            cur=body
            try:
                for p in path: cur=cur[p]
                if isinstance(cur,list): return [float(x) for x in cur]
            except Exception: pass
    if isinstance(body,list) and body and isinstance(body[0],(int,float)): return [float(x) for x in body]
    raise RuntimeError('Cannot find embedding vector. Raw: '+json.dumps(body,ensure_ascii=False)[:2000])
def embed(text,c):
    if not c.get('embed_path'): raise RuntimeError('Embedding endpoint not configured. Ask Linh to confirm Kizuna embed_path/request/auth first.')
    body=req_json(c.get('embed_method','POST'),c['base_url'].rstrip('/')+'/'+c['embed_path'].lstrip('/'),headers(c),json_body={'input':text,'model':c.get('embed_model','bge-m3')})
    return extract_embedding(body), body
@app.get('/',response_class=HTMLResponse)
def home(request:Request): return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':load_cfg()})
@app.post('/config',response_class=HTMLResponse)
def config(request:Request, base_url:str=Form(''), api_key:str=Form(''), ocr_path:str=Form(''), embed_path:str=Form(''), auth_header:str=Form('Authorization'), auth_prefix:str=Form('Bearer'), ocr_method:str=Form('GET'), embed_method:str=Form('POST')):
    c={'base_url':base_url,'api_key':api_key,'ocr_path':ocr_path,'embed_path':embed_path,'auth_header':auth_header,'auth_prefix':auth_prefix,'ocr_method':ocr_method,'embed_method':embed_method}; save_cfg(c)
    return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':c,'msg':'Config saved locally'})
@app.post('/test',response_class=HTMLResponse)
def test(request:Request):
    c=load_cfg(); msg='Need confirmed base_url + endpoint before testing Kizuna.'
    if c.get('base_url'):
        try: msg=json.dumps(req_json('GET',c['base_url'].rstrip('/')+'/',headers(c)),ensure_ascii=False,indent=2)
        except Exception as e: msg=str(e)
    return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':c,'msg':msg})

def list_items(body):
    if isinstance(body, dict):
        for k in ['data','items','results','collections','documents']:
            if isinstance(body.get(k), list): return body[k]
    return body if isinstance(body, list) else []
@app.post('/collections',response_class=HTMLResponse)
def collections(request:Request):
    c=load_cfg()
    try:
        body=req_json('GET',c['base_url'].rstrip()+'/rag/collections',headers(c))
        return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':c,'collections':list_items(body),'msg':'Collections loaded'})
    except Exception as e: return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':c,'err':str(e)})
@app.post('/documents',response_class=HTMLResponse)
def documents(request:Request, collection_id:str=Form(...)):
    c=load_cfg()
    try:
        body=req_json('GET',c['base_url'].rstrip()+'/rag/documents',headers(c),params={'collection_id':collection_id})
        return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':c,'collection_id':collection_id,'documents':list_items(body),'msg':'Documents loaded'})
    except Exception as e: return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':c,'collection_id':collection_id,'err':str(e)})

@app.post('/ocr',response_class=HTMLResponse)
def ocr(request:Request, document_id:str=Form(...), filename:str=Form('document.md')):
    c=load_cfg()
    if not c.get('ocr_path'): return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':c,'err':'OCR endpoint not configured. Ask Linh for endpoint/request/auth confirmation.'})
    try:
        url=c['base_url'].rstrip()+'/'+c['ocr_path'].lstrip('/').replace('{document_id}',document_id)
        body=req_json(c.get('ocr_method','GET'),url,headers(c),json_body={'document_id':document_id} if c.get('ocr_method')!='GET' else None, params={'document_id':document_id} if c.get('ocr_method')=='GET' else None)
        md=clean_md(extract_markdown(body)); (DATA/f'{document_id}.md').write_text(md)
        return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':c,'document_id':document_id,'filename':filename,'markdown':md,'msg':'OCR fetched; chunks preview ready'})
    except Exception as e: return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':c,'err':str(e)})
@app.post('/ingest',response_class=HTMLResponse)
def ingest(request:Request, document_id:str=Form(...), filename:str=Form('document.md')):
    c=load_cfg(); p=DATA/f'{document_id}.md'
    if not p.exists(): return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':c,'err':'Fetch OCR first; markdown file not found.'})
    try:
        cs=chunks(p.read_text()); client=QdrantClient(url=QDRANT); pts=[]; dim=None
        for idx,content in enumerate(cs):
            vec,_=embed(content,c); dim=len(vec); pts.append(PointStruct(id=str(uuid.uuid4()), vector=vec, payload={'document_id':document_id,'filename':filename,'chunk_index':idx,'content':content}))
        if dim and not client.collection_exists(COLLECTION): client.create_collection(COLLECTION, vectors_config=VectorParams(size=dim,distance=Distance.COSINE))
        client.upsert(COLLECTION, pts)
        return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':c,'msg':f'Ingested chunks={len(cs)}, embedding_dim={dim}, qdrant_insert_count={len(pts)}'})
    except Exception as e: return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':c,'err':str(e)})
@app.post('/search',response_class=HTMLResponse)
def search(request:Request, query:str=Form(...), top_k:int=Form(5)):
    c=load_cfg()
    try:
        vec,_=embed(query,c); client=QdrantClient(url=QDRANT)
        
        try:
            res=client.query_points(collection_name=COLLECTION, query=vec, limit=top_k, with_payload=True).points
        except AttributeError:
            res=client.search(collection_name=COLLECTION, query_vector=vec, limit=top_k, with_payload=True)
        return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':c,'query':query,'results':res,'msg':f'Query embedding_dim={len(vec)}'})
    except Exception as e: return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':c,'err':str(e)})


@app.post('/chat',response_class=HTMLResponse)
def chat(request:Request, chat_query:str=Form(...), top_k:int=Form(5)):
    c=load_cfg()
    try:
        vec,_=embed(chat_query,c); client=QdrantClient(url=QDRANT)
        try:
            res=client.query_points(collection_name=COLLECTION, query=vec, limit=top_k, with_payload=True).points
        except AttributeError:
            res=client.search(collection_name=COLLECTION, query_vector=vec, limit=top_k, with_payload=True)
        bullets=[]
        for i,r in enumerate(res,1):
            payload=r.payload or {}; content=(payload.get('content') or '').strip()
            bullets.append({'rank':i,'score':r.score,'document_id':payload.get('document_id'), 'filename':payload.get('filename'), 'chunk_index':payload.get('chunk_index'), 'content':content})
        return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':c,'chat_query':chat_query,'chat_results':bullets,'msg':'Mini chat is retrieval-only: showing top relevant chunks, no LLM generation.'})
    except Exception as e: return templates.TemplateResponse(request,'index.html',{'request':request,'cfg':c,'chat_query':chat_query,'err':str(e)})
