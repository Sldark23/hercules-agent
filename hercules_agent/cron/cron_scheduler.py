# Cron Jobs module for Hercules Agent
# Scheduled task management

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Awaitable
from enum import Enum
from datetime import datetime, timedelta
import asyncio
import logging
import uuid
import json
import os

logger = logging.getLogger(__name__)


class CronStatus(Enum):
    """Job status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class CronSchedule(Enum):
    """Simple schedule presets"""
    ONCE = "once"
    MINUTE = "every_minute"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class CronJob:
    """Scheduled job definition"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    prompt: str = ""
    schedule: str = ""  # cron expression or preset
    enabled: bool = True
    repeat: Optional[int] = None  # None = infinite
    repeat_count: int = 0
    skills: List[str] = field(default_factory=list)
    model: Optional[Dict[str, str]] = None  # {provider, model}
    delivery: str = "origin"  # origin, local, telegram, discord
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    status: CronStatus = CronStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    context_from: List[str] = field(default_factory=list)  # job IDs to inject


@dataclass
class CronConfig:
    """Cron configuration"""
    enabled: bool = True
    max_concurrent: int = 3
    timeout: int = 3600  # seconds
    storage_path: str = "~/.hermes/cron/jobs.json"


class CronExecutor:
    """Executes scheduled jobs"""
    
    def __init__(self, agent_executor: Callable[[str, List[str], Optional[Dict]], Awaitable[str]] = None):
        self.agent_executor = agent_executor
        self._running_jobs: Dict[str, asyncio.Task] = {}
    
    async def execute(self, job: CronJob) -> str:
        """Execute a cron job"""
        if not self.agent_executor:
            return "Agent executor not configured"
        
        job.status = CronStatus.RUNNING
        job.last_run = datetime.now()
        
        try:
            result = await asyncio.wait_for(
                self.agent_executor(job.prompt, job.skills, job.model),
                timeout=job.timeout if hasattr(job, 'timeout') else 3600
            )
            
            job.status = CronStatus.COMPLETED
            job.result = result
            job.error = None
            job.repeat_count += 1
            
            return result
            
        except asyncio.TimeoutError:
            job.status = CronStatus.FAILED
            job.error = "Execution timeout"
            raise
            
        except Exception as e:
            job.status = CronStatus.FAILED
            job.error = str(e)
            raise


class CronScheduler:
    """Manages scheduled jobs"""
    
    def __init__(self, config: CronConfig = None, executor: CronExecutor = None):
        self.config = config or CronConfig()
        self.executor = executor or CronExecutor()
        self.jobs: Dict[str, CronJob] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        
        self._load_jobs()
    
    def _load_jobs(self):
        """Load jobs from storage"""
        path = os.path.expanduser(self.config.storage_path)
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    for job_data in data.get('jobs', []):
                        job = CronJob(**job_data)
                        self.jobs[job.id] = job
                logger.info(f"Loaded {len(self.jobs)} cron jobs")
            except Exception as e:
                logger.error(f"Failed to load cron jobs: {e}")
    
    def _save_jobs(self):
        """Save jobs to storage"""
        path = os.path.expanduser(self.config.storage_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        data = {
            'jobs': [
                {
                    'id': job.id,
                    'name': job.name,
                    'prompt': job.prompt,
                    'schedule': job.schedule,
                    'enabled': job.enabled,
                    'repeat': job.repeat,
                    'repeat_count': job.repeat_count,
                    'skills': job.skills,
                    'model': job.model,
                    'delivery': job.delivery,
                    'last_run': job.last_run.isoformat() if job.last_run else None,
                    'next_run': job.next_run.isoformat() if job.next_run else None,
                    'status': job.status.value,
                    'result': job.result,
                    'error': job.error,
                    'context_from': job.context_from,
                }
                for job in self.jobs.values()
            ]
        }
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _parse_schedule(self, schedule: str) -> timedelta:
        """Parse schedule string to timedelta"""
        presets = {
            CronSchedule.ONCE.value: None,
            CronSchedule.MINUTE.value: timedelta(minutes=1),
            CronSchedule.HOURLY.value: timedelta(hours=1),
            CronSchedule.DAILY.value: timedelta(days=1),
            CronSchedule.WEEKLY.value: timedelta(weeks=1),
            CronSchedule.MONTHLY.value: timedelta(days=30),
        }
        
        if schedule in presets:
            return presets[schedule]
        
        # Default to daily
        return timedelta(days=1)
    
    def _calculate_next_run(self, job: CronJob) -> Optional[datetime]:
        """Calculate next run time"""
        if not job.enabled:
            return None
        
        interval = self._parse_schedule(job.schedule)
        if interval is None:
            return None
        
        if job.last_run:
            return job.last_run + interval
        
        return datetime.now() + interval
    
    def add_job(self, job: CronJob) -> str:
        """Add a new cron job"""
        job.next_run = self._calculate_next_run(job)
        self.jobs[job.id] = job
        self._save_jobs()
        
        # Start scheduler if not running
        if not self._running:
            asyncio.create_task(self._scheduler_loop())
        
        logger.info(f"Added cron job: {job.name} ({job.id})")
        return job.id
    
    def remove_job(self, job_id: str) -> bool:
        """Remove a cron job"""
        if job_id in self.jobs:
            del self.jobs[job_id]
            self._save_jobs()
            return True
        return False
    
    def pause_job(self, job_id: str) -> bool:
        """Pause a job"""
        if job_id in self.jobs:
            self.jobs[job_id].enabled = False
            self.jobs[job_id].status = CronStatus.PAUSED
            self._save_jobs()
            return True
        return False
    
    def resume_job(self, job_id: str) -> bool:
        """Resume a job"""
        if job_id in self.jobs:
            self.jobs[job_id].enabled = True
            self.jobs[job_id].status = CronStatus.PENDING
            self.jobs[job_id].next_run = self._calculate_next_run(self.jobs[job_id])
            self._save_jobs()
            return True
        return False
    
    async def run_job(self, job_id: str, manual: bool = False) -> str:
        """Manually run a job"""
        if job_id not in self.jobs:
            return f"Job not found: {job_id}"
        
        job = self.jobs[job_id]
        
        # Inject context from previous jobs if configured
        context = ""
        if job.context_from:
            for prev_id in job.context_from:
                if prev_id in self.jobs and self.jobs[prev_id].result:
                    context += f"\n\n[{prev_id} output]:\n{self.jobs[prev_id].result}"
        
        full_prompt = context + "\n\n" + job.prompt if context else job.prompt
        
        try:
            result = await self.executor.execute(job)
            
            if not manual:
                job.next_run = self._calculate_next_run(job)
            
            self._save_jobs()
            return result
            
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            return f"Error: {str(e)}"
    
    async def _scheduler_loop(self):
        """Main scheduler loop"""
        self._running = True
        
        while self._running:
            try:
                now = datetime.now()
                
                # Check each job
                for job in self.jobs.values():
                    if not job.enabled:
                        continue
                    
                    if job.next_run and now >= job.next_run:
                        # Check repeat limit
                        if job.repeat is not None and job.repeat_count >= job.repeat:
                            job.enabled = False
                            continue
                        
                        # Run job
                        asyncio.create_task(self._run_job_async(job))
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(10)
    
    async def _run_job_async(self, job: CronJob):
        """Run job asynchronously"""
        try:
            await self.executor.execute(job)
        except Exception as e:
            logger.error(f"Job {job.id} failed: {e}")
        finally:
            job.next_run = self._calculate_next_run(job)
            self._save_jobs()
    
    def get_job(self, job_id: str) -> Optional[CronJob]:
        """Get job by ID"""
        return self.jobs.get(job_id)
    
    def list_jobs(self) -> List[Dict[str, Any]]:
        """List all jobs"""
        return [
            {
                "id": job.id,
                "name": job.name,
                "schedule": job.schedule,
                "enabled": job.enabled,
                "status": job.status.value,
                "last_run": job.last_run.isoformat() if job.last_run else None,
                "next_run": job.next_run.isoformat() if job.next_run else None,
                "repeat_count": job.repeat_count,
            }
            for job in self.jobs.values()
        ]
    
    def stop(self):
        """Stop scheduler"""
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()