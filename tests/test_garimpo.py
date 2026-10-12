import os,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'garimpo/.local/share/garimpo'))
import config,readers,search
from indexer import Indexer,sensitive,walk
from store import Store
from embed import EmbedError

class FakeEmbedder:
 """Bag-of-words vectors: deterministic stand-in for EmbeddingGemma."""
 images=False
 def __init__(self,online=True):self.online=online
 def status(self):return (self.online,'fake')
 def _vec(self,text):
  v=np.zeros(64,np.float32)
  for w in search.words(text):v[hash(w)%64]+=1
  n=np.linalg.norm(v);return v/n if n else v
 def query(self,text):
  if not self.online:raise EmbedError('offline',offline=True)
  return self._vec(text)
 def documents(self,pairs):return np.array([self._vec(t) for _,t in pairs])
 def image(self,data):return None

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
 def test_numeric(self):self.assertTrue(readers.mostly_numeric('1,2,3\n4,5,6\n'*50))

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
 def test_code_prefix(self):self.assertEqual(search.parse('code: retry backoff'),('code','retry backoff'))

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

if __name__=='__main__':unittest.main()
