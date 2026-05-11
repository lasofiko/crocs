import { useEffect, useMemo, useState } from 'react';
import './animation.css';
import { DEFAULT_PAGE_SIZE, fetchScheduleAnimationPage, fetchScheduleExcel } from '../../api/scheduleApi';
import Header from '../../components/Header/header';
import PlaybackBar from '../../components/PlaybackBar/PlaybackBar';
import WeekStationsBoard from '../../components/WeekStationsBoard/WeekStationsBoard';
import type { AnimationScheduleItem } from '../../types/schedule';
import { buildWeekSlidesFromSchedule } from '../../utils/buildWeekSlides';
import { dedupeScheduleRows } from '../../utils/dedupeScheduleRows';
import { filterValidScheduleRows } from '../../utils/filterValidScheduleRows';
import { formatDay, formatHour } from '../../utils/scheduleFormat';

const DEFAULT_HEADER_DATA: AnimationScheduleItem = {
    date: '',
    hour: 7,
    station: '',
    employeeIds: [],
    expectedPeopleCount: 0,
    expectationIndicator: '',
    day: 1,
};

/** Рабочие часы: дольше на слайд; ночь 0–6 — быстро «проматываем» до открытия */
const WORKING_SLIDE_MS = 5000;
const OFF_HOURS_SLIDE_MS = 180;
const WORK_START_HOUR = 7;
const WORK_END_HOUR = 23;

function Animation() {
    const [scheduleData, setScheduleData] = useState<AnimationScheduleItem[]>([DEFAULT_HEADER_DATA]);
    const [currentIndex, setCurrentIndex] = useState(0);
    const [isPaused, setIsPaused] = useState(false);
    const [fetchHint, setFetchHint] = useState<string | null>(null);

    const slides = useMemo(() => buildWeekSlidesFromSchedule(scheduleData), [scheduleData]);

    const currentSlide = slides[currentIndex] ?? slides[0];
    const isWorkingTime =
        currentSlide !== undefined &&
        currentSlide.hour >= WORK_START_HOUR &&
        currentSlide.hour <= WORK_END_HOUR;

    const slideCount = slides.length;

    useEffect(() => {
        setCurrentIndex((i) => Math.min(i, Math.max(0, slideCount - 1)));
    }, [slideCount]);

    useEffect(() => {
        let cancelled = false;
        let page = 0;
        const acc: AnimationScheduleItem[] = [];
        let seededIndex = false;

        (async () => {
            try {
                while (!cancelled) {
                    const res = await fetchScheduleAnimationPage({ page, pageSize: DEFAULT_PAGE_SIZE });
                    const valid = filterValidScheduleRows(res.items);
                    acc.push(...valid);
                    const merged = dedupeScheduleRows(acc);

                    if (cancelled) {
                        break;
                    }

                    if (merged.length > 0) {
                        setScheduleData(merged);
                        if (!seededIndex) {
                            setCurrentIndex(0);
                            seededIndex = true;
                        }
                    } else if (page === 0) {
                        setScheduleData([DEFAULT_HEADER_DATA]);
                        setCurrentIndex(0);
                    }

                    if (!res.hasMore) {
                        break;
                    }

                    page += 1;
                }

                if (!cancelled) {
                    const finalRows = dedupeScheduleRows(acc);
                    setFetchHint(
                        finalRows.length === 0
                            ? 'Нет строк для экрана: положите schedule.xlsx в artifacts (после run_pipeline) и перезапустите API, либо проверьте CROCS_ARTIFACTS_DIR.'
                            : null,
                    );
                }
            } catch (err) {
                console.error('schedule fetch', err);
                if (!cancelled) {
                    setScheduleData([DEFAULT_HEADER_DATA]);
                    setCurrentIndex(0);
                    setFetchHint(
                        'Не удалось загрузить /api/schedule/animation. Запустите uvicorn на :8000 и npm run dev (прокси /api), откройте консоль браузера.',
                    );
                }
            }
        })();

        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        if (isPaused || slideCount <= 1) {
            return undefined;
        }

        const hour = currentSlide.hour;
        const isNight =
            Number.isFinite(hour) && hour >= 0 && hour < WORK_START_HOUR;
        const delayMs = isNight ? OFF_HOURS_SLIDE_MS : WORKING_SLIDE_MS;

        const timeoutId = window.setTimeout(() => {
            setCurrentIndex((index) => (index + 1) % slideCount);
        }, delayMs);

        return () => window.clearTimeout(timeoutId);
    }, [isPaused, slideCount, currentIndex, currentSlide.hour]);

    const handleSaveSchedule = () => {
        fetchScheduleExcel()
            .then((file) => {
                const fileUrl = URL.createObjectURL(file);
                const link = document.createElement('a');

                link.href = fileUrl;
                link.download = 'schedule.xlsx';
                link.click();
                URL.revokeObjectURL(fileUrl);
            })
            .catch(() => {});
    };

    const handleSeek = (index: number) => {
        setCurrentIndex(Math.max(0, Math.min(index, slideCount - 1)));
    };

    const handlePrevHour = () => {
        setCurrentIndex((index) => (index - 1 + slideCount) % slideCount);
    };

    const handleNextHour = () => {
        setCurrentIndex((index) => (index + 1) % slideCount);
    };

    if (!currentSlide) {
        return null;
    }

    return (
        <main className="animation">
            <Header
                day={isWorkingTime ? formatDay(currentSlide.day) : ''}
                time={formatHour(currentSlide.hour)}
                onSaveSchedule={handleSaveSchedule}
                screenDimmed={!isWorkingTime}
            />

            <section className="animation__stations" aria-label="Станции">
                {fetchHint ? (
                    <p className="animation__fetch-hint" role="status">
                        {fetchHint}
                    </p>
                ) : null}
                <WeekStationsBoard items={currentSlide.items} />
            </section>

            <PlaybackBar
                currentIndex={currentIndex}
                slideCount={slideCount}
                isPaused={isPaused}
                onPauseToggle={() => setIsPaused((value) => !value)}
                onPrevHour={handlePrevHour}
                onNextHour={handleNextHour}
                onSeek={handleSeek}
            />
        </main>
    );
}

export default Animation;
