"""One-shot local-time reception deadline, independent of Bot connectivity."""
from datetime import datetime, timedelta
from threading import Event, Thread

from pydantic import BaseModel, Field


class ScheduleSettings(BaseModel):
    enabled: bool = False
    time: str = Field(default='23:00', pattern=r'^([01][0-9]|2[0-3]):[0-5][0-9]$')


class ReceptionSchedule:
    def __init__(self, services, bot, clock=datetime.now):
        self.services, self.bot, self.clock = services, bot, clock
        self.stopped = Event()
        self.thread = None

    def status(self):
        return self.services.persistence_service.get_state().get('reception_schedule', {})

    def configure(self, settings):
        now = self.clock()
        hour, minute = map(int, settings.time.split(':'))
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due <= now:
            due += timedelta(days=1)
        schedule = {'enabled': settings.enabled, 'time': settings.time,
                    'due_at': due.isoformat() if settings.enabled else None,
                    'result': ''}
        self.services.persistence_service.mutate_state(
            lambda state: state.update(reception_schedule=schedule))
        return schedule

    def tick(self):
        persistence = self.services.persistence_service
        closed = False
        with persistence.serialized():
            schedule = self.status()
            if not schedule.get('enabled') or self.clock() < datetime.fromisoformat(schedule['due_at']):
                return
            def expire(state):
                nonlocal closed
                closed = state['is_open']
                state['is_open'] = False
                state['reception_schedule'] = {**schedule, 'enabled': False,
                    'result': '指定時刻になったため受付を終了しました' if closed else '受付終了済みのため予約を完了しました'}
                state['logs'].append(state['reception_schedule']['result'])
            # Close reception and consume the deadline in the same SQLite transaction.
            persistence.mutate_state(expire)
        if closed:
            self.bot.announce_closed()

    def start(self):
        self.tick()
        def run():
            while not self.stopped.wait(0.5):
                try:
                    self.tick()
                except Exception:
                    # Keep checking after transient database contention.
                    import logging
                    logging.getLogger(__name__).exception('受付終了時刻の確認に失敗しました')
        self.thread = Thread(target=run, daemon=True, name='reception-schedule')
        self.thread.start()

    def stop(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=5)
