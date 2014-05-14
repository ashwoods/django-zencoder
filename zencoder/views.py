import json
import base64
import hmac
import hashlib
import datetime
import os

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from .conf import settings
from .models import Video, Job


def notify(request):
    # job = get_object_or_404(Job, pk=job_id)
    data = json.loads(request.body)
    job = get_object_or_404(Job, job_id=data.get("job", {}).get("id"))
    job.notify(data)
    job.save()
    return HttpResponse(content="", status=204)


@require_http_methods(["POST"])
@staff_member_required
def encode(request, video_id):
    video = get_object_or_404(Video, pk=video_id)

    job = Job(video=video)
    data = job.start()

    return HttpResponse(json.dumps(data), content_type="application/json")


@require_http_methods(["POST", "GET"])
@staff_member_required
def video(request, video_id=None):
    status_code = 200
    if request.method == "GET":
        video = get_object_or_404(Video, pk=video_id)
    else:
        if video_id is None:
            video = Video.objects.create()
            status_code = 201
        else:
            # Let's just make sure this video exists
            video = get_object_or_404(Video, pk=video_id)
        video.name = request.POST["name"]

    expiration = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
    path = os.path.join(settings.VIDEO_ENCODING_DIRECTORY, str(video.id), video.name)

    video.input = "s3://{}/{}".format(settings.VIDEO_ENCODING_BUCKET, path)
    video.save()

    # Now let's build a signature for this upload, using:
    # http://docs.aws.amazon.com/AmazonS3/latest/dev/HTTPPOSTForms.html
    policy_dict = {
        "expiration": expiration.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
        "conditions": [
            {"bucket": settings.VIDEO_ENCODING_BUCKET},
            {"acl": "private"},
            {"success_action_status": '201'},
            ["$key", path],
            ["content-length-range", 0, 1073741824],
        ]
    }

    policy_document = json.dumps(policy_dict)
    policy = base64.b64encode(policy_document)

    signature = hmac.new(
        settings.AWS_SECRET_ACCESS_KEY,
        policy,
        hashlib.sha1).digest()

    upload_endpoint = "https://{}.s3.amazonaws.com".format(settings.VIDEO_ENCODING_BUCKET)

    contents = {
        "id": video.id,
        "path": video.input,
        "upload_endpoint": upload_endpoint,
        'AWSAccessKeyId': settings.AWS_ACCESS_KEY_ID,
        'acl': 'private',
        'success_action_status': '201',
        'policy': policy,
        'signature': base64.b64encode(signature)
    }
    return HttpResponse(json.dumps(contents), status=status_code, content_type="application/json")