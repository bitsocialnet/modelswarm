import { Suspense, use } from 'react';
import { catalogueSnapshot, demoEntry, formatCount, type Model } from '../data/catalogue';
import { starterPicks } from '../data/catalogue-selection';
import { SectionHead } from '../components/section-head/section-head';
import { ModelCard } from '../components/model-card/model-card';
import { ArrowRightIcon } from '../components/icons/icons';
import section from './section.module.css';
import styles from './models.module.css';

export function Models() {
  return (
    <section id='models' className={section.section} aria-labelledby='models-title'>
      <div className='wrap'>
        <div className={styles.head}>
          <SectionHead
            source='catalogue/README.md'
            id='models-title'
            lede='Small chat models from the catalogue, each under 500 MB. Open the torrent in any BitTorrent client; the signed one can also be verified piece by piece with the CLI.'
          >
            Start with a small model
          </SectionHead>
        </div>
        <Suspense fallback={<Picks models={[demoEntry]} />}>
          <Loaded />
        </Suspense>
      </div>
    </section>
  );
}

function Loaded() {
  const snapshot = use(catalogueSnapshot());
  return <Picks models={snapshot?.models ?? [demoEntry]} total={snapshot?.models.length} />;
}

function Picks({ models, total }: { models: Model[]; total?: number }) {
  const picks = starterPicks.flatMap((pick) => {
    const model = models.find(({ id }) => id === pick.id);
    return model ? [{ pick, model }] : [];
  });
  return (
    <>
      <div className={styles.grid}>
        {picks.map(({ pick, model }) => (
          <ModelCard key={model.id} model={model} name={pick.name} description={pick.description} format={pick.format} />
        ))}
      </div>
      <div className={styles.more}>
        <a className='button' href='./catalogue.html'>
          {total ? `Browse all ${formatCount(total)} models` : 'Browse all models'}
          <ArrowRightIcon size={14} />
        </a>
        <p>Seeder counts come from the Pirate Face index at its last observation.</p>
      </div>
    </>
  );
}
