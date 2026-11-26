import { Topbar } from './components/topbar/topbar';
import { Hero } from './sections/hero';
import { Swarm } from './sections/swarm';
import { Models } from './sections/models';
import { Proofs } from './sections/proofs';
import { Handles } from './sections/handles';
import { Assembly } from './sections/assembly';
import { Thesis } from './sections/thesis';
import { Compare } from './sections/compare';
import { Roadmap } from './sections/roadmap';
import { Faq } from './sections/faq';
import { Join } from './sections/join';
import { Footer } from './sections/footer';

export function App() {
  return (
    <>
      <a className='skip' href='#main'>
        Skip to content
      </a>
      <Topbar />
      <main id='main'>
        <Hero />
        <Swarm />
        <Models />
        <Proofs />
        <Handles />
        <Assembly />
        <Thesis />
        <Compare />
        <Roadmap />
        <Faq />
        <Join />
      </main>
      <Footer />
    </>
  );
}
