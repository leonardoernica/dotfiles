import os,sys,tempfile,time,unittest,zipfile,zlib
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'garimpo/.local/share/garimpo'))
import config,readers,search
from indexer import Indexer,sensitive,walk
from store import Store
from embed import EmbedError,Embedder

class FakeEmbedder:
 """Bag-of-words vectors: deterministic stand-in for EmbeddingGemma."""
 images=False
 def __init__(self,online=True):self.online=online
 def status(self):return (self.online,'fake')
 def _vec(self,text):
  v=np.zeros(64,np.float32)
  for w in search.words(text):v[zlib.crc32(w.encode())%64]+=1
  n=np.linalg.norm(v);return v/n if n else v
 def query(self,text,scope='files',picture=False):
  if not self.online:raise EmbedError('offline',offline=True)
  return (self._vec(text),self._vec(text)) if picture else self._vec(text)
 def documents(self,pairs,quick=False):return np.array([self._vec(t) for _,t in pairs])
 def image(self,data):return None
 def audio(self,data):return None

def cfg_for(root,**extra):
 cfg=dict(config.DEFAULTS,roots=[root],code_roots=[],ocr=False,dimensions=64,model='fake');cfg.update(extra);return cfg

class ReaderTests(unittest.TestCase):
 def test_chunks_track_lines(self):
  text='\n\n'.join(f'paragrafo {i} '+'x'*300 for i in range(6))
  out=readers.chunks(text,size=700)
  self.assertGreater(len(out),1);self.assertEqual(out[0][0],1);self.assertTrue(all(b>a for (a,_),(b,_) in zip(out,out[1:])))
 def test_name_text_skips_hashes(self):
  self.assertEqual(readers.name_text(Path('0118c249-6782-3dc3.pdf')),'')
  self.assertEqual(readers.name_text(Path('plano_de_governo-2024.pdf')),'plano de governo 2024')
 def test_docx(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'contrato.docx'
   with zipfile.ZipFile(p,'w') as z:z.writestr('word/document.xml','<w:document><w:p><w:t>Cláusula sobre animais</w:t></w:p></w:document>')
   self.assertIn('Cláusula sobre animais',readers.read_office(p)[0][1])
 def test_kinds(self):
  self.assertEqual([readers.kind(Path(n)) for n in ('a.PDF','b.jpeg','c.mkv','d.py','e.zip')],['pdf','image','video','code','other'])
 def test_audio_windows_skip_short_tail(self):
  with tempfile.TemporaryDirectory() as d:
   for secs,expect in ((141,[0,20,40,60,80,100,120]),(12,[0]),(45,[0,20])):
    p=Path(d)/f'a{secs}.wav'
    import subprocess;subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'sine=frequency=440:duration={secs}',str(p)],check=True)
    self.assertEqual([t for t,_ in readers.audio_windows(p,120)],expect,secs)
 def test_numeric(self):self.assertTrue(readers.mostly_numeric('1,2,3\n4,5,6\n'*50))
 def test_prose_versus_data(self):
  self.assertTrue(readers.prose('O inquilino pode manter animais de estimação, desde que avise o proprietário.'))
  self.assertFalse(readers.prose('{"maquina_nome": "COLADEIRA 2", "id": 33, "turno": "B", "ok": true, "ts": 1748982434}'))
  self.assertFalse(readers.prose('rst:0xc (SW_CPU_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT) clk_drv:0x00,q_drv:0x00,d_drv:0x00'))
 def test_ocr_keeps_confident_words(self):
  head='level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
  row=lambda line,conf,word:f'5\t1\t1\t1\t{line}\t1\t0\t0\t9\t9\t{conf}\t{word}\n'
  tsv=head+row(1,96,'Pagamento')+row(1,91,'recusado')+row(1,12,'~_<ANCA')+row(2,88,'código')+row(2,90,'E4021')
  done=lambda out:type('R',(),{'stdout':out.encode()})()
  with patch('shutil.which',return_value='/usr/bin/tesseract'),patch('subprocess.run',return_value=done(tsv)):
   self.assertEqual(readers.ocr(Path('x.png'),'por'),'Pagamento recusado\ncódigo E4021')
  with patch('shutil.which',return_value='/usr/bin/tesseract'),patch('subprocess.run',return_value=done(head+row(1,30,'URANCA')+row(1,95,'AGIL'))):
   self.assertEqual(readers.ocr(Path('logo.png'),'por'),'')  # logos and photos: no text at all

class PrivacyTests(unittest.TestCase):
 def test_sensitive_names(self):
  for n in ('id_rsa','server.pem','.env','minhas_senhas.txt','client_secret.json'):self.assertTrue(sensitive(n),n)
  self.assertFalse(sensitive('relatorio.pdf'))
 def test_walk_skips_hidden_secret_and_code(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   for rel in ('notas.md','.ssh/config','node_modules/x/readme.md','secrets/a.txt','app.py','id_rsa'):
    (root/rel).parent.mkdir(parents=True,exist_ok=True);(root/rel).write_text('x')
   self.assertEqual([p.name for p,_,_ in walk(cfg_for(root))],['notas.md'])

class CodeWalkTests(unittest.TestCase):
 def test_git_repo_respects_gitignore_and_keeps_tracked_dot_folders(self):
  import subprocess
  with tempfile.TemporaryDirectory() as d:
   repo=Path(d)/'repo'
   for rel in ('src/app.py','.github/ci.py','build.py','ignored/gen.py','.env'):
    (repo/rel).parent.mkdir(parents=True,exist_ok=True);(repo/rel).write_text('x=1')
   (repo/'.gitignore').write_text('ignored/\n');subprocess.run(['git','init','-q',str(repo)],check=True)
   names=sorted(str(p.relative_to(repo)) for p,_,_ in walk(cfg_for(Path(d)/'none',code_roots=[Path(d)])))
   self.assertEqual(names,['.github/ci.py','build.py','src/app.py'])

class LiveTests(unittest.TestCase):
 def tree(self,root):
  files=['notas.md','fotos/praia.jpg','.oculto/x.md','node_modules/a.md','x_cache/b.md','secrets/c.md','id_rsa','app.py',
         'proj/package.json','proj/README.md','proj/shot.png','dados/'+'x'*0+'keep.pdf','download.crdownload','musica.mp3']
  files+=[f'dump/{i}.txt' for i in range(210)]
  for rel in files:(root/rel).parent.mkdir(parents=True,exist_ok=True);(root/rel).write_text('conteúdo')
 def test_classify_matches_full_walk(self):
  from watcher import classify
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'r';self.tree(root);cfg=cfg_for(root)
   walked={p for p,_,_ in walk(cfg)}
   every={Path(dp)/n for dp,_,ns in os.walk(root) for n in ns}
   self.assertEqual({p for p in every if classify(p,cfg)},walked)
   self.assertIn(root/'proj/shot.png',walked);self.assertNotIn(root/'proj/README.md',walked);self.assertNotIn(root/'dump/1.txt',walked)
 def wait(self,idx,cond,timeout=6):
  end=time.time()+timeout
  while time.time()<end:
   idx.drain(quiet=0.3)
   if cond():return True
   time.sleep(0.1)
  return False
 def test_inotify_indexes_new_moved_and_deleted_files(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'r';root.mkdir();cfg=cfg_for(root);store=Store(Path(d)/'i.db')
   idx=Indexer(cfg,store,FakeEmbedder(),log=lambda m:None);idx.use_vectors=True;idx.start_watching()
   time.sleep(0.3)
   s=search.Searcher(store,FakeEmbedder(),cfg);found=lambda q:[os.path.basename(r['path']) for r in s.search(q)[1]]
   (root/'baixado.md').write_text('orçamento da reforma da cozinha')
   self.assertTrue(self.wait(idx,lambda:'baixado.md' in found('reforma cozinha')))
   tmp=Path(d)/'fora';(tmp/'sub').mkdir(parents=True);(tmp/'sub/viagem.md').write_text('roteiro de viagem para Lisboa')
   os.rename(tmp,root/'pasta')  # a whole folder moved in (like unzipping elsewhere and moving)
   self.assertTrue(self.wait(idx,lambda:'viagem.md' in found('Lisboa')))
   (root/'pasta/sub/novo.md').write_text('arquivo criado depois na pasta nova')  # the new folder is watched too
   self.assertTrue(self.wait(idx,lambda:'novo.md' in found('criado depois')))
   (root/'baixado.md').unlink()
   self.assertTrue(self.wait(idx,lambda:'baixado.md' not in found('reforma cozinha')))
   import shutil;shutil.rmtree(root/'pasta')
   self.assertTrue(self.wait(idx,lambda:not found('Lisboa')))
   store.db.close()

class SearchTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)/'docs';root.mkdir()
  (root/'contrato_aluguel.md').write_text('O inquilino pode manter animais de estimação.\n\nMulta por atraso de pagamento.')
  (root/'receita.txt').write_text('Bolo de cenoura com cobertura de chocolate.')
  (root/'erro.txt').write_text('payment declined error code E4021')
  self.root=root;self.cfg=cfg_for(root)
  self.store=Store(Path(self.tmp.name)/'index.db');self.emb=FakeEmbedder()
  with patch.object(config,'STATE',Path(self.tmp.name)):Indexer(self.cfg,self.store,self.emb,log=lambda m:None).cycle()
  self.searcher=search.Searcher(self.store,self.emb,self.cfg)
 def tearDown(self):self.store.db.close();self.tmp.cleanup()
 def names(self,q):return [os.path.basename(r['path']) for r in self.searcher.search(q)[1]]
 def test_semantic_and_keyword(self):
  self.assertEqual(self.names('animais de estimação')[0],'contrato_aluguel.md')
  self.assertEqual(self.names('E4021')[0],'erro.txt')
 def test_accent_insensitive_prefix(self):self.assertEqual(self.names('cenou')[0],'receita.txt')
 def test_unchanged_files_are_skipped(self):
  idx=Indexer(self.cfg,self.store,self.emb,log=lambda m:None)
  with patch.object(config,'STATE',Path(self.tmp.name)),patch.object(idx,'process') as process:idx.cycle()
  process.assert_not_called()
 def test_deleted_file_leaves_index(self):
  (self.root/'receita.txt').unlink()
  with patch.object(config,'STATE',Path(self.tmp.name)):Indexer(self.cfg,self.store,self.emb,log=lambda m:None).cycle()
  self.assertNotIn('receita.txt',self.names('bolo cenoura'))
 def test_model_arrival_reuses_extracted_text(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'r';root.mkdir();(root/'nota.md').write_text('reunião sobre orçamento anual')
   store=Store(Path(d)/'i.db');cfg=cfg_for(root)
   with patch.object(config,'STATE',Path(d)):
    Indexer(cfg,store,FakeEmbedder(online=False),log=lambda m:None).cycle()
    self.assertEqual(store.matrix('files','fake')[0].size,0)
    idx=Indexer(cfg,store,FakeEmbedder(),log=lambda m:None)
    with patch.object(idx,'process') as process:idx.cycle()
    process.assert_not_called()
   self.assertGreater(store.matrix('files','fake')[0].size,0)
   s=search.Searcher(store,FakeEmbedder(),cfg);self.assertEqual(os.path.basename(s.search('orçamento')[1][0]['path']),'nota.md')
   store.db.close()
 def test_offline_falls_back_to_keywords(self):
  s=search.Searcher(self.store,FakeEmbedder(online=False),self.cfg)
  self.assertEqual(os.path.basename(s.search('cenoura')[1][0]['path']),'receita.txt');self.assertIsNotNone(s.semantic_error)
 def test_spreadsheets_are_exact_words_only(self):
  import zipfile as z
  p=self.root/'vendas.xlsx'
  with z.ZipFile(p,'w') as f:f.writestr('xl/sharedStrings.xml','<sst><si><t>cliente Joaquim pedido 7781</t></si></sst>')
  with patch.object(config,'STATE',Path(self.tmp.name)):Indexer(self.cfg,self.store,self.emb,log=lambda m:None).cycle()
  rows=self.store.db.execute("select c.vec from chunks c join files f on f.id=c.file_id where f.path like '%vendas.xlsx' and c.loc is not null").fetchall()
  self.assertTrue(rows and all(r[0] is None for r in rows));self.assertEqual(self.names('7781')[0],'vendas.xlsx')
 def test_media_modality_is_recentred(self):
  q=self.emb.query('chuva forte');rng=np.random.default_rng(0)
  def ortho():
   v=rng.normal(size=64);v-=(v@q)*q;return v/np.linalg.norm(v)
  target=0.3*q+np.sqrt(1-0.09)*ortho()  # raw similarity 0.3: far below the text threshold
  for i in range(25):
   other=self.store.upsert_file(self.root/f'outro{i}.mp3',0,0,'audio','files','done','fake')
   self.store.add_chunks(other,[(0,'',ortho(),None,'a')],'fake')
  fid=self.store.upsert_file(self.root/'som.mp3',0,0,'audio','files','done','fake')
  self.store.add_chunks(fid,[(999,'',target,None,'a')],'fake');self.store.bump()
  hits=[r for r in self.searcher.search('chuva forte')[1] if r['path'].endswith('som.mp3')]
  self.assertEqual(hits[0]['loc'],999)
 def test_identical_copies_fold_into_one(self):
  (self.root/'contrato_aluguel (1).md').write_bytes((self.root/'contrato_aluguel.md').read_bytes())
  with patch.object(config,'STATE',Path(self.tmp.name)):Indexer(self.cfg,self.store,self.emb,log=lambda m:None).cycle()
  hits=[r for r in self.searcher.search('animais de estimação')[1] if 'contrato_aluguel' in r['path']]
  self.assertEqual(len(hits),1);self.assertEqual(hits[0]['copies'],1)
 def test_whole_words_before_prefixes(self):
  (self.root/'app.txt').write_text('Botão de suporte no rodapé do aplicativo.')
  (self.root/'loja.txt').write_text('A bota de couro marrom voltou ao estoque.')
  with patch.object(config,'STATE',Path(self.tmp.name)):Indexer(self.cfg,self.store,self.emb,log=lambda m:None).cycle()
  self.assertEqual(self.searcher._keyword('bota','files')[0].keys(),{c for c,_ in self.store.keyword('"bota"','files')})
  self.assertNotIn('app.txt',search.Searcher(self.store,FakeEmbedder(online=False),self.cfg).search('bota')[1][0]['path'])
  self.assertEqual(self.searcher._keyword('cenou','files')[1],'prefix')  # unfinished word: prefix as a fallback
 def test_upgrade_drops_vectors_of_data_chunks(self):
  (self.root/'dump.txt').write_text('{"maquina_nome": "COLADEIRA 2", "id": 33, "turno": "B", "ok": true, "ts": 1748982434}')
  self.store.set('quality',99)
  with patch.object(config,'STATE',Path(self.tmp.name)):Indexer(self.cfg,self.store,self.emb,log=lambda m:None).cycle()
  vec=lambda:self.store.db.execute("select c.vec from chunks c join files f on f.id=c.file_id where f.path like '%dump.txt' and c.loc is not null").fetchone()[0]
  self.assertIsNone(vec())  # new files: data gets no vector
  fid=self.store.file(self.root/'dump.txt')[0]
  self.store.db.execute("update chunks set vec=?, model='fake' where file_id=? and loc is not null",(np.ones(64,np.float16).tobytes(),fid));self.store.db.commit()
  self.store.set('quality',0)
  with patch.object(config,'STATE',Path(self.tmp.name)):Indexer(self.cfg,self.store,self.emb,log=lambda m:None).cycle()
  self.assertIsNone(vec());self.assertTrue(all(d for d, in self.store.db.execute('select digest from files')))
  self.assertEqual(self.names('COLADEIRA')[0],'dump.txt')  # still found by its words
 def test_upgrade_redoes_ocr_of_screenshots(self):
  from PIL import Image
  Image.new('RGB',(40,40),'white').save(self.root/'captura.png')
  idx=Indexer(dict(self.cfg,ocr=True),self.store,self.emb,log=lambda m:None);idx.langs='por'
  with patch.object(config,'STATE',Path(self.tmp.name)),patch('readers.ocr',return_value='URANCA ~_<ANCA AGILIDADE CUID texto ruim'):idx.cycle()
  self.store.set('quality',0)
  with patch.object(config,'STATE',Path(self.tmp.name)),patch('readers.ocr',return_value='Pagamento recusado pelo banco emissor'):idx.cycle()
  fid=self.store.file(self.root/'captura.png')[0]
  self.assertEqual([t for _,l,t in self.store.chunks_of(fid) if l is not None],['Pagamento recusado pelo banco emissor'])
  self.assertEqual(self.names('banco emissor')[0],'captura.png')
 def test_long_media_do_not_win_by_chance(self):
  q=self.emb.query('chuva forte');rng=np.random.default_rng(1)
  def near(sim):
   v=rng.normal(size=64);v-=(v@q)*q;v/=np.linalg.norm(v);return sim*q+np.sqrt(1-sim*sim)*v
  for i in range(30):
   other=self.store.upsert_file(self.root/f'foto{i}.jpg',0,0,'image','files','done','fake')
   self.store.add_chunks(other,[(0,'',near(0.0),None,'i')],'fake')
  photo=self.store.upsert_file(self.root/'chuva.jpg',0,0,'image','files','done','fake')
  self.store.add_chunks(photo,[(0,'',near(0.25),None,'i')],'fake')
  video=self.store.upsert_file(self.root/'filme.mp4',0,0,'video','files','done','fake')
  self.store.add_chunks(video,[(s,'',near(0.27 if s==0 else 0.0),None,'i') for s in range(0,160,4)],'fake');self.store.bump()
  media=[os.path.basename(r['path']) for r in self.searcher.search('chuva forte')[1] if r.get('media')]
  self.assertEqual(media[0],'chuva.jpg')  # one strong frame out of 40 counts less than one strong photo
 def test_asking_for_a_kind_puts_it_first(self):
  self.assertEqual(search.parse('foto da praia'),('files','foto da praia'))
  self.assertEqual({m for m,ws in search.WANTS.items() if set(search.content_words('foto da praia'))&ws},{'i'})
 def test_apps_by_meaning(self):
  apps=[('chess.desktop','Chess Overlay','Chess Overlay · Setas sobre o tabuleiro de xadrez'),('calc.desktop','Calc','Calc · planilha')]
  apps+=[(f'a{i}.desktop',f'App {i}',f'App {i} · ferramenta numero {i}') for i in range(20)]
  self.searcher.search('tabuleiro de xadrez')
  self.assertEqual(self.searcher.app_hits(apps)[0][0],'chess.desktop')
  self.assertTrue(any(k.startswith('app:') for k, in self.store.db.execute('select key from meta')))  # vectors kept
 def test_code_prefix(self):self.assertEqual(search.parse('code: retry backoff'),('code','retry backoff'))

class EmbedderTests(unittest.TestCase):
 def setUp(self):self.e=Embedder(dict(config.DEFAULTS,dimensions=2))
 def test_prefixes_and_truncation(self):
  calls=[]
  def req(path,body=None,timeout=0,url=None):calls.append(body);return {'data':[{'index':0,'embedding':[3.0,4.0,9.0]}]}
  with patch.object(self.e,'_request',side_effect=req):v=self.e.query('retry',scope='code')
  self.assertEqual(calls[0]['input'],['task: code retrieval | query: retry']);self.assertTrue(np.allclose(v,[.6,.8]))
 def test_media_uses_server_marker_and_refreshes_it(self):
  props=iter([{'media_marker':'<m1>','modalities':{'vision':True}},{'media_marker':'<m2>','modalities':{'vision':True}}])
  def req(path,body=None,timeout=0,url=None):
   if path=='/props':return next(props)
   if body['input'][0]['prompt_string']=='<m1>':raise EmbedError('Failed to tokenize prompt')
   return {'data':[{'index':0,'embedding':[1.0,0.0]}]}
  with patch.object(self.e,'_request',side_effect=req):self.assertIsNotNone(self.e.image(b'jpg'))
  self.assertEqual(self.e.marker,'<m2>')
 def test_no_audio_encoder(self):
  with patch.object(self.e,'_request',return_value={'media_marker':'<m>','modalities':{'vision':True}}):self.assertIsNone(self.e.audio(b'wav'))

class CalculatorTests(unittest.TestCase):
 def setUp(self):
  import gi;gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
  import ui;self.calc=ui.calculate;self.highlight=ui.highlight
 def test_math(self):
  self.assertEqual(self.calc('2+2'),'4');self.assertEqual(self.calc('1,5*2'),'3');self.assertEqual(self.calc('1000*1000'),'1.000.000')
  self.assertEqual(self.calc('sqrt(16)'),'4')
 def test_not_math(self):
  for q in ('firefox','2024','__import__("os")','9**99999','1/0'):self.assertIsNone(self.calc(q),q)
 def test_highlight_with_accents(self):
  self.assertIn('>Ação</span>',self.highlight('Ação & reação','acao'))
  self.assertIn('&amp;',self.highlight('Ação & reação','acao'))
  self.assertNotIn('<span',self.highlight('o fanatismo destrói','de'));self.assertNotIn('<span',self.highlight('reação','acao'))

class OpenTests(unittest.TestCase):
 def setUp(self):
  import gi;gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
  import ui;self.ui=ui
 def handler(self,app_id):
  from unittest.mock import MagicMock
  h=MagicMock();h.get_id.return_value=app_id;return h
 def test_pdf_page_in_browser(self):
  h=self.handler('com.google.Chrome.desktop')
  with patch.object(self.ui.Gio.AppInfo,'get_default_for_type',return_value=h):
   self.ui.open_file(dict(path='/tmp/a b.pdf',kind='pdf',loc=7),dict(config.DEFAULTS))
  self.assertEqual(h.launch_uris.call_args.args[0],['file:///tmp/a%20b.pdf#page=7'])
 def test_video_and_audio_at_second(self):
  for kind,path in (('video','/tmp/v.mp4'),('audio','/tmp/a.mp3')):
   with patch.object(self.ui.Gio.AppInfo,'get_default_for_type',return_value=self.handler('mpv.desktop')),patch.object(self.ui,'spawn') as spawn:
    self.ui.open_file(dict(path=path,kind=kind,loc=29),dict(config.DEFAULTS))
   self.assertEqual(spawn.call_args.args[0],['mpv','--force-window','--start=29',path])
 def test_code_at_line(self):
  with patch.object(self.ui.Gio.AppInfo,'get_default_for_type',return_value=None),patch.object(self.ui.GLib,'find_program_in_path',return_value='/usr/bin/code'),patch.object(self.ui,'spawn') as spawn:
   self.ui.open_file(dict(path='/p/x.py',kind='code',loc=120),dict(config.DEFAULTS))
  self.assertEqual(spawn.call_args.args[0],['code','-g','/p/x.py:120'])

if __name__=='__main__':unittest.main()
