import uuid

from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from holodeck.utils import get_widget_type_choices, load_class_by_string, \
    metric_to_shard_mapper, sample_to_shard_mapper


class Dashboard(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(User, null=True)

    def __unicode__(self):
        return self.name


class Metric(models.Model):
    name = models.CharField(max_length=255)
    dashboard = models.ForeignKey('holodeck.Dashboard')
    widget_type = models.CharField(
        max_length=64,
        choices=get_widget_type_choices()
    )
    api_key = models.CharField(
        max_length=32,
        unique=True,
        blank=True,
        null=True
    )

    def __unicode__(self):
        return self.name

    @classmethod
    def generate_api_key(cls):
        return uuid.uuid4().hex

    def render(self):
        return load_class_by_string(self.widget_type)().render(self)

    @property
    def sample_set(self):
        return Sample.objects.filter(metric_id=self.id).using(
            'shard_%s' % metric_to_shard_mapper(self))

    def save(self, *args, **kwargs):
        if not self.api_key:
            self.api_key = Metric.generate_api_key()
        super(Metric, self).save(*args, **kwargs)


class Sample(models.Model):
    metric_id = models.IntegerField(max_length=64)
    integer_value = models.IntegerField()
    string_value = models.CharField(max_length=64)
    timestamp = models.DateTimeField()

    def save(self, *args, **kwargs):
        self.full_clean()
        kwargs.update({'using': 'shard_%s' % sample_to_shard_mapper(self)})
        super(Sample, self).save(*args, **kwargs)


@receiver(post_delete, sender=Metric)
def metric_post_delete_handler(sender, instance, **kwargs):
    """
    Because relation between sample and metric is handled on the application
    level ensure deletion of samples on metric delete.
    """
    instance.sample_set.all().delete()
