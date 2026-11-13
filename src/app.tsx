import { Topbar } from './components/topbar/topbar';
import { Hero } from './sections/hero';
import { Assembly } from './sections/assembly';
import { Thesis } from './sections/thesis';
import { Parts } from './sections/parts';
import { Compare } from './sections/compare';
import { Roadmap } from './sections/roadmap';
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
        <Assembly />
        <Thesis />
        <Parts />
        <Compare />
        <Roadmap />
        <Join />
      </main>
      <Footer />
    </>
  );
}
