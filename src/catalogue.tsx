import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/oxanium/index.css';
import '@fontsource-variable/red-hat-mono/index.css';
import './index.css';
import { Topbar } from './components/topbar/topbar';
import { demoModel } from './data/demo-model';
import { Footer } from './sections/footer';
import styles from './release.module.css';

function Catalogue() {
  return (
    <>
      <a className='skip' href='#main'>
        Skip to content
      </a>
      <Topbar catalogue />
      <main className={`wrap ${styles.main}`} id='main'>
        <header className={styles.intro}>
          <h1>Models</h1>
          <p>Browse signed releases of open-weight models.</p>
        </header>
        <article className={styles.catalogueEntry}>
          <div>
            <h2>
              <a href={demoModel.page}>{demoModel.title}</a>
            </h2>
            <p>{demoModel.description}</p>
            <p className={styles.catalogueMeta}>
              {demoModel.format} · {demoModel.quantization} · {demoModel.size} · {demoModel.license}
            </p>
            <p className={styles.catalogueMeta}>Signed by the {demoModel.publisher}</p>
          </div>
          <a className='button' href={demoModel.page}>
            View release
          </a>
        </article>
      </main>
      <Footer />
    </>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Catalogue />
  </StrictMode>,
);
