import Overview from "@/components/Overview";
import { ErrorBox } from "@/components/ui";
import { pubFetch } from "@/lib/api";
import { homeDate } from "@/lib/homeOverview";
import PublisherIcon from "@/components/PublisherIcon";
import HomeSignal from "@/components/HomeSignal";
import "./home.css";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let data: any = null;
  let error = "";
  try {
    data = await pubFetch("/api/overview");
  } catch (e: any) {
    error = e?.message ?? "нет связи с Control API";
  }
  return (
    <div className="home-page">
      <input id="home-signal-pause" className="home-motion-input sr-only" type="checkbox" aria-label="Пауза анимации фона" />
      <HomeSignal />
      <header className="home-header">
        <div>
          <div className="home-kicker"><PublisherIcon name="dashboard" /> Управление каналом</div>
          <h1>Главная</h1>
          <p>Работа бота, ближайшая публикация и очередь</p>
        </div>
        <div className="home-header-tools">
          <label htmlFor="home-signal-pause" className="home-motion-label">
            <span className="home-motion-icon" aria-hidden="true" />
            <span className="home-motion-running">Пауза фона</span>
            <span className="home-motion-paused">Оживить фон</span>
          </label>
          <div className="home-date"><PublisherIcon name="calendar" /> {homeDate(new Date())}</div>
        </div>
      </header>
      {error ? <ErrorBox message={error} /> : <Overview initial={data} />}
    </div>
  );
}
