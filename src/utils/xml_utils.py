from datetime import datetime

SEQUENCE_NAME_PREFIX = "SchnittmAIster"


def generate_timestamped_sequence_name(task_name: str, job_id: str) -> str:
    """
    Name the XMEML sequence after the service, the task, the current time and the job.

    The start of the job ID keeps the names of two jobs of the same task in the same second apart, so they do
    not write into the same result folder.

    :param task_name: Name of the task that produced the sequence.
    :param job_id: ID of the job.
    :return: A string like 'SchnittmAIster_generic_2026-10-29_10-15-42_3f9a2c'.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{SEQUENCE_NAME_PREFIX}_{task_name}_{timestamp}_{job_id[:6]}"
